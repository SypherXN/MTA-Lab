"""Link cursor_usage rows to automation_runs and backfill cursor_run_id on runs."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.lane_service import ensure_primary_lane, get_primary_lane_id

EFFECTIVE_COST_SQL = "COALESCE(NULLIF(cost_usd, 0), estimated_cost_usd, 0)"

FUZZY_AUTOMATION_NAMES = (
    "mta-explorer",
    "mta-ticker-scout",
)


@dataclass(frozen=True)
class UsageGroup:
    cursor_run_id: str
    session_at: datetime
    usage_ids: tuple[int, ...]


@dataclass
class UsageRelinkResult:
    exact_usage_linked: int = 0
    fuzzy_usage_linked: int = 0
    runs_cursor_run_id_backfilled: int = 0
    scout_runs_created: int = 0
    remaining_unlinked: int = 0


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _relink_exact(conn: sqlite3.Connection) -> int:
    before = conn.execute(
        "SELECT COUNT(*) AS c FROM cursor_usage WHERE run_id IS NOT NULL"
    ).fetchone()["c"]
    conn.execute(
        """
        UPDATE cursor_usage
        SET run_id = (
            SELECT r.id FROM automation_runs r
            WHERE r.cursor_run_id = cursor_usage.cursor_run_id
            LIMIT 1
        )
        WHERE run_id IS NULL
          AND cursor_run_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM automation_runs r
            WHERE r.cursor_run_id = cursor_usage.cursor_run_id
          )
        """
    )
    after = conn.execute(
        "SELECT COUNT(*) AS c FROM cursor_usage WHERE run_id IS NOT NULL"
    ).fetchone()["c"]
    return int(after - before)


def _backfill_run_cursor_ids(conn: sqlite3.Connection) -> int:
    result = conn.execute(
        """
        UPDATE automation_runs
        SET cursor_run_id = (
            SELECT u.cursor_run_id
            FROM cursor_usage u
            WHERE u.run_id = automation_runs.id
              AND u.cursor_run_id IS NOT NULL
              AND TRIM(u.cursor_run_id) != ''
            ORDER BY u.id
            LIMIT 1
        )
        WHERE (cursor_run_id IS NULL OR TRIM(cursor_run_id) = '')
          AND EXISTS (
            SELECT 1 FROM cursor_usage u
            WHERE u.run_id = automation_runs.id
              AND u.cursor_run_id IS NOT NULL
              AND TRIM(u.cursor_run_id) != ''
          )
        """
    )
    return int(result.rowcount)


def _load_unlinked_groups(conn: sqlite3.Connection) -> list[UsageGroup]:
    rows = conn.execute(
        """
        SELECT id, cursor_run_id, reconciled_at
        FROM cursor_usage
        WHERE run_id IS NULL
          AND cursor_run_id IS NOT NULL
          AND TRIM(cursor_run_id) != ''
        ORDER BY reconciled_at
        """
    ).fetchall()
    grouped: dict[str, list[tuple[int, datetime]]] = {}
    for row in rows:
        parsed = _parse_ts(row["reconciled_at"])
        if parsed is None:
            continue
        grouped.setdefault(row["cursor_run_id"], []).append((int(row["id"]), parsed))

    groups: list[UsageGroup] = []
    for cursor_run_id, items in grouped.items():
        session_at = min(ts for _, ts in items)
        groups.append(
            UsageGroup(
                cursor_run_id=cursor_run_id,
                session_at=session_at,
                usage_ids=tuple(item[0] for item in items),
            )
        )
    groups.sort(key=lambda group: group.session_at)
    return groups


def _load_runs_missing_cursor_id(
    conn: sqlite3.Connection,
    automation_name: str,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT id, run_at, automation_name, lane_id
            FROM automation_runs
            WHERE automation_name = ?
              AND (cursor_run_id IS NULL OR TRIM(cursor_run_id) = '')
            ORDER BY run_at
            """,
            (automation_name,),
        )
    )


def _link_group_to_run(
    conn: sqlite3.Connection,
    *,
    group: UsageGroup,
    run_id: int,
) -> int:
    conn.execute(
        "UPDATE automation_runs SET cursor_run_id = ? WHERE id = ?",
        (group.cursor_run_id, run_id),
    )
    placeholders = ",".join("?" for _ in group.usage_ids)
    conn.execute(
        f"UPDATE cursor_usage SET run_id = ? WHERE id IN ({placeholders})",
        (run_id, *group.usage_ids),
    )
    return len(group.usage_ids)


def _fuzzy_relink_automation(
    conn: sqlite3.Connection,
    *,
    automation_name: str,
    groups: list[UsageGroup],
    tolerance: timedelta,
) -> tuple[int, list[UsageGroup]]:
    runs = _load_runs_missing_cursor_id(conn, automation_name)
    if not runs:
        return 0, groups

    linked = 0
    remaining = list(groups)
    for run in runs:
        run_at = _parse_ts(run["run_at"])
        if run_at is None:
            continue
        best_idx: int | None = None
        best_delta = tolerance + timedelta(seconds=1)
        for idx, group in enumerate(remaining):
            delta = abs(group.session_at - run_at)
            if delta <= tolerance and delta < best_delta:
                best_delta = delta
                best_idx = idx
        if best_idx is None:
            continue
        group = remaining.pop(best_idx)
        linked += _link_group_to_run(conn, group=group, run_id=int(run["id"]))
    return linked, remaining


def _create_scout_run_from_group(
    conn: sqlite3.Connection,
    group: UsageGroup,
) -> int:
    lane_id = conn.execute(
        "SELECT id FROM simulation_lanes WHERE name = 'ticker-explorer' LIMIT 1"
    ).fetchone()
    resolved_lane = int(lane_id["id"]) if lane_id else get_primary_lane_id(conn)
    lane = conn.execute(
        "SELECT strategy_version, plan_version FROM simulation_lanes WHERE id = ?",
        (resolved_lane,),
    ).fetchone()
    strategy = conn.execute(
        "SELECT mode FROM strategies WHERE version = ?",
        (lane["strategy_version"],),
    ).fetchone()
    run_at = group.session_at.isoformat()
    cursor = conn.execute(
        """
        INSERT INTO automation_runs (
            run_at, automation_name, run_type, market_summary, status,
            strategy_version, plan_version, mode, errors_json, cursor_run_id,
            lane_id
        ) VALUES (?, 'mta-ticker-scout', 'reconciliation_only', ?, 'completed',
                  ?, ?, ?, '[]', ?, ?)
        """,
        (
            run_at,
            "Backfilled from Cursor usage CSV (scout automation).",
            lane["strategy_version"],
            lane["plan_version"],
            strategy["mode"] if strategy else "research",
            group.cursor_run_id,
            resolved_lane,
        ),
    )
    run_id = int(cursor.lastrowid)
    _link_group_to_run(conn, group=group, run_id=run_id)
    return run_id


def relink_cursor_usage(
    conn: sqlite3.Connection,
    *,
    tolerance_minutes: int = 120,
    create_scout_runs: bool = True,
) -> UsageRelinkResult:
    """Exact match, backfill run IDs, then time-based fuzzy match for explorer/scout."""
    result = UsageRelinkResult()
    result.exact_usage_linked = _relink_exact(conn)
    result.runs_cursor_run_id_backfilled = _backfill_run_cursor_ids(conn)

    tolerance = timedelta(minutes=tolerance_minutes)
    groups = _load_unlinked_groups(conn)

    explorer_linked, groups = _fuzzy_relink_automation(
        conn,
        automation_name="mta-explorer",
        groups=groups,
        tolerance=tolerance,
    )
    result.fuzzy_usage_linked += explorer_linked

    if groups:
        wide_linked, groups = _fuzzy_relink_automation(
            conn,
            automation_name="mta-explorer",
            groups=groups,
            tolerance=timedelta(hours=6),
        )
        result.fuzzy_usage_linked += wide_linked

    scout_linked, groups = _fuzzy_relink_automation(
        conn,
        automation_name="mta-ticker-scout",
        groups=groups,
        tolerance=tolerance,
    )
    result.fuzzy_usage_linked += scout_linked

    result.runs_cursor_run_id_backfilled += _backfill_run_cursor_ids(conn)
    result.exact_usage_linked += _relink_exact(conn)

    if create_scout_runs:
        for group in list(groups):
            if group.session_at.weekday() != 6:
                continue
            linked_count = len(group.usage_ids)
            _create_scout_run_from_group(conn, group)
            result.scout_runs_created += 1
            groups.remove(group)
            result.fuzzy_usage_linked += linked_count

    result.runs_cursor_run_id_backfilled += _backfill_run_cursor_ids(conn)
    result.exact_usage_linked += _relink_exact(conn)

    result.remaining_unlinked = int(
        conn.execute(
            "SELECT COUNT(*) AS c FROM cursor_usage WHERE run_id IS NULL"
        ).fetchone()["c"]
    )
    return result
