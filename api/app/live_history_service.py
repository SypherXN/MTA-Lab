"""Combined real-money history across live lane promotions."""

import json
import sqlite3

from app.lane_service import get_lane, list_lanes
from app.schemas import (
    LaneLivePeriodOut,
    LiveTradingHistoryOut,
    LiveTradingSnapshotOut,
)
from app.safety import LIVE_ACTIONS
from app.snapshot_service import get_portfolio_snapshots

LIVE_ACTIONS_SQL = ", ".join(f"'{action}'" for action in sorted(LIVE_ACTIONS))


def _count_runs_in_period(
    conn: sqlite3.Connection,
    lane_id: int,
    started_at: str,
    ended_at: str | None,
) -> int:
    query = """
        SELECT COUNT(*) AS c FROM automation_runs
        WHERE lane_id = ? AND run_at >= ?
    """
    params: list = [lane_id, started_at]
    if ended_at:
        query += " AND run_at < ?"
        params.append(ended_at)
    return int(conn.execute(query, params).fetchone()["c"])


def _count_real_orders_in_period(
    conn: sqlite3.Connection,
    lane_id: int,
    started_at: str,
    ended_at: str | None,
) -> int:
    query = f"""
        SELECT COUNT(*) AS c
        FROM decisions d
        JOIN automation_runs r ON r.id = d.run_id
        WHERE r.lane_id = ?
          AND r.run_at >= ?
          AND lower(d.action) IN ({LIVE_ACTIONS_SQL})
    """
    params: list = [lane_id, started_at]
    if ended_at:
        query += " AND r.run_at < ?"
        params.append(ended_at)
    return int(conn.execute(query, params).fetchone()["c"])


def _period_equity_change(
    conn: sqlite3.Connection,
    lane_id: int,
    started_at: str,
    ended_at: str | None,
) -> tuple[float | None, int]:
    until = ended_at
    snapshots = get_portfolio_snapshots(
        conn,
        lane_id=lane_id,
        since=started_at,
        until=until,
        limit=500,
    )
    if len(snapshots) < 2:
        return None, len(snapshots)
    first_equity = float(snapshots[0]["total_equity_usd"])
    last_equity = float(snapshots[-1]["total_equity_usd"])
    return last_equity - first_equity, len(snapshots)


def list_live_periods(conn: sqlite3.Connection) -> list[LaneLivePeriodOut]:
    rows = conn.execute(
        """
        SELECT
            p.id, p.lane_id, p.started_at, p.ended_at,
            l.name AS lane_name, l.strategy_version, l.plan_version
        FROM lane_live_periods p
        JOIN simulation_lanes l ON l.id = p.lane_id
        ORDER BY p.started_at ASC, p.id ASC
        """
    ).fetchall()

    periods: list[LaneLivePeriodOut] = []
    for row in rows:
        ended_at = row["ended_at"]
        equity_change, snapshot_count = _period_equity_change(
            conn,
            int(row["lane_id"]),
            row["started_at"],
            ended_at,
        )
        periods.append(
            LaneLivePeriodOut(
                id=int(row["id"]),
                lane_id=int(row["lane_id"]),
                lane_name=row["lane_name"],
                strategy_version=row["strategy_version"],
                plan_version=row["plan_version"],
                started_at=row["started_at"],
                ended_at=ended_at,
                is_current=ended_at is None,
                snapshot_count=snapshot_count,
                run_count=_count_runs_in_period(
                    conn, int(row["lane_id"]), row["started_at"], ended_at
                ),
                real_order_count=_count_real_orders_in_period(
                    conn, int(row["lane_id"]), row["started_at"], ended_at
                ),
                equity_change_usd=equity_change,
            )
        )
    return periods


def get_combined_live_snapshots(
    conn: sqlite3.Connection,
) -> list[LiveTradingSnapshotOut]:
    rows = conn.execute(
        """
        SELECT
            p.id AS period_id, p.lane_id, p.started_at, p.ended_at,
            l.name AS lane_name
        FROM lane_live_periods p
        JOIN simulation_lanes l ON l.id = p.lane_id
        ORDER BY p.started_at ASC, p.id ASC
        """
    ).fetchall()

    combined: list[LiveTradingSnapshotOut] = []
    previous_lane_id: int | None = None
    for row in rows:
        lane_id = int(row["lane_id"])
        snapshots = get_portfolio_snapshots(
            conn,
            lane_id=lane_id,
            since=row["started_at"],
            until=row["ended_at"],
            limit=500,
        )
        for index, snapshot in enumerate(snapshots):
            is_handoff = index == 0 and previous_lane_id is not None and previous_lane_id != lane_id
            combined.append(
                LiveTradingSnapshotOut(
                    snapshot_at=snapshot["snapshot_at"],
                    total_equity_usd=float(snapshot["total_equity_usd"]),
                    lane_id=lane_id,
                    lane_name=row["lane_name"],
                    period_id=int(row["period_id"]),
                    is_handoff=is_handoff,
                )
            )
        if snapshots:
            previous_lane_id = lane_id
    return combined


def get_live_trading_history(conn: sqlite3.Connection) -> LiveTradingHistoryOut:
    live_lane = next(
        (lane for lane in list_lanes(conn) if lane.lane_role == "live" and lane.status == "active"),
        None,
    )
    periods = list_live_periods(conn)
    combined_snapshots = get_combined_live_snapshots(conn)
    combined_equity_change: float | None = None
    if len(combined_snapshots) >= 2:
        combined_equity_change = (
            combined_snapshots[-1].total_equity_usd - combined_snapshots[0].total_equity_usd
        )
    total_real_orders = sum(period.real_order_count for period in periods)
    return LiveTradingHistoryOut(
        current_live_lane_id=live_lane.id if live_lane else None,
        current_live_lane_name=live_lane.name if live_lane else None,
        periods=periods,
        combined_snapshots=combined_snapshots,
        combined_equity_change_usd=combined_equity_change,
        total_real_orders=total_real_orders,
    )


def backfill_live_periods(conn: sqlite3.Connection) -> None:
    """Reconstruct live periods from promotion alerts when table is empty."""
    count = conn.execute("SELECT COUNT(*) AS c FROM lane_live_periods").fetchone()["c"]
    if count > 0:
        return

    alerts = conn.execute(
        """
        SELECT created_at, payload_json, entity_id
        FROM alerts
        WHERE alert_type = 'live_lane_promoted'
        ORDER BY created_at ASC, id ASC
        """
    ).fetchall()

    for alert in alerts:
        lane_id: int | None = None
        if alert["payload_json"]:
            try:
                payload = json.loads(alert["payload_json"])
                lane_id = int(payload.get("lane_id") or 0) or None
            except (json.JSONDecodeError, TypeError, ValueError):
                lane_id = None
        if lane_id is None and alert["entity_id"]:
            try:
                lane_id = int(alert["entity_id"])
            except (TypeError, ValueError):
                lane_id = None
        if lane_id is None:
            continue

        started_at = alert["created_at"]
        conn.execute(
            "UPDATE lane_live_periods SET ended_at = ? WHERE ended_at IS NULL",
            (started_at,),
        )
        conn.execute(
            """
            INSERT INTO lane_live_periods (lane_id, started_at)
            VALUES (?, ?)
            """,
            (lane_id, started_at),
        )

    live_row = conn.execute(
        """
        SELECT id, created_at, updated_at
        FROM simulation_lanes
        WHERE lane_role = 'live' AND status = 'active'
        LIMIT 1
        """
    ).fetchone()
    if live_row is None:
        return

    lane_id = int(live_row["id"])
    open_period = conn.execute(
        """
        SELECT id FROM lane_live_periods
        WHERE lane_id = ? AND ended_at IS NULL
        LIMIT 1
        """,
        (lane_id,),
    ).fetchone()
    if open_period is not None:
        return

    first_run = conn.execute(
        "SELECT MIN(run_at) AS t FROM automation_runs WHERE lane_id = ?",
        (lane_id,),
    ).fetchone()
    started_at = (
        first_run["t"]
        or live_row["updated_at"]
        or live_row["created_at"]
    )
    conn.execute(
        "UPDATE lane_live_periods SET ended_at = ? WHERE ended_at IS NULL",
        (started_at,),
    )
    conn.execute(
        """
        INSERT INTO lane_live_periods (lane_id, started_at)
        VALUES (?, ?)
        """,
        (lane_id, started_at),
    )
