"""Simulation lane management — isolated portfolios per strategy/plan approach."""

from datetime import datetime, timezone

import sqlite3

from app.config import settings
from app.plan_service import get_agent_plan_by_version
from app.schemas import (
    LaneCreate,
    LaneOut,
    LanePromoteResponse,
    LaneUpdate,
    StrategyOut,
)
from app.safety import get_strategy_by_version

PRIMARY_LANE_ID = 1
VALID_LANE_ROLES = frozenset({"research", "shadow", "live"})
VALID_LANE_STATUSES = frozenset({"active", "paused", "archived"})


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_lane(row: sqlite3.Row) -> LaneOut:
    return LaneOut(
        id=row["id"],
        name=row["name"],
        strategy_version=row["strategy_version"],
        plan_version=row["plan_version"],
        lane_role=row["lane_role"],
        status=row["status"],
        initial_cash_usd=float(row["initial_cash_usd"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _ensure_lane_cash_row(conn: sqlite3.Connection, lane_id: int, cash_usd: float) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO simulated_cash (lane_id, cash_usd, updated_at)
        VALUES (?, ?, ?)
        """,
        (lane_id, cash_usd, _iso_now()),
    )


def _validate_strategy_version(conn: sqlite3.Connection, version: str) -> None:
    row = conn.execute(
        "SELECT version FROM strategies WHERE version = ? LIMIT 1",
        (version,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Strategy version {version} not found")


def _validate_plan_version(conn: sqlite3.Connection, version: str) -> None:
    get_agent_plan_by_version(conn, version)


def _close_open_live_periods(conn: sqlite3.Connection, ended_at: str) -> None:
    conn.execute(
        "UPDATE lane_live_periods SET ended_at = ? WHERE ended_at IS NULL",
        (ended_at,),
    )


def _start_live_period(conn: sqlite3.Connection, lane_id: int, started_at: str) -> None:
    conn.execute(
        """
        INSERT INTO lane_live_periods (lane_id, started_at)
        VALUES (?, ?)
        """,
        (lane_id, started_at),
    )


def get_lane(conn: sqlite3.Connection, lane_id: int) -> LaneOut:
    row = conn.execute(
        """
        SELECT id, name, strategy_version, plan_version, lane_role, status,
               initial_cash_usd, created_at, updated_at
        FROM simulation_lanes
        WHERE id = ?
        """,
        (lane_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Lane {lane_id} not found")
    return _row_to_lane(row)


def get_primary_lane_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT id FROM simulation_lanes
        WHERE status = 'active'
        ORDER BY id ASC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return PRIMARY_LANE_ID
    return int(row["id"])


def resolve_lane_id(conn: sqlite3.Connection, lane_id: int | None) -> int:
    ensure_primary_lane(conn)
    if lane_id is None:
        return get_primary_lane_id(conn)
    lane = get_lane(conn, lane_id)
    if lane.status != "active":
        raise ValueError(f"Lane {lane_id} is {lane.status}; only active lanes accept runs")
    return lane_id


def list_lanes(
    conn: sqlite3.Connection,
    *,
    include_archived: bool = False,
) -> list[LaneOut]:
    query = """
        SELECT id, name, strategy_version, plan_version, lane_role, status,
               initial_cash_usd, created_at, updated_at
        FROM simulation_lanes
    """
    if not include_archived:
        query += " WHERE status != 'archived'"
    query += " ORDER BY id ASC"
    return [_row_to_lane(row) for row in conn.execute(query)]


def get_strategy_for_lane(conn: sqlite3.Connection, lane_id: int) -> StrategyOut:
    lane = get_lane(conn, lane_id)
    return get_strategy_by_version(conn, lane.strategy_version)


def lane_allows_live_trading(lane: LaneOut, strategy: StrategyOut) -> bool:
    return (
        lane.lane_role == "live"
        and strategy.mode == "live"
        and strategy.trading_enabled
        and not strategy.kill_switch
    )


def create_lane(conn: sqlite3.Connection, payload: LaneCreate) -> LaneOut:
    _validate_strategy_version(conn, payload.strategy_version)
    _validate_plan_version(conn, payload.plan_version)

    lane_role = (payload.lane_role or "research").lower()
    if lane_role not in VALID_LANE_ROLES:
        raise ValueError("lane_role must be research, shadow, or live")

    if lane_role == "live":
        existing_live = conn.execute(
            "SELECT id FROM simulation_lanes WHERE lane_role = 'live' AND status = 'active'"
        ).fetchone()
        if existing_live is not None:
            raise ValueError("An active live lane already exists")

    initial_cash = (
        payload.initial_cash_usd
        if payload.initial_cash_usd is not None
        else settings.initial_simulated_cash
    )
    now = _iso_now()
    cursor = conn.execute(
        """
        INSERT INTO simulation_lanes (
            name, strategy_version, plan_version, lane_role, status,
            initial_cash_usd, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (
            payload.name.strip(),
            payload.strategy_version,
            payload.plan_version,
            lane_role,
            initial_cash,
            now,
            now,
        ),
    )
    lane_id = int(cursor.lastrowid)
    _ensure_lane_cash_row(conn, lane_id, initial_cash)
    if lane_role == "live":
        _close_open_live_periods(conn, now)
        _start_live_period(conn, lane_id, now)
    return get_lane(conn, lane_id)


def update_lane(conn: sqlite3.Connection, lane_id: int, payload: LaneUpdate) -> LaneOut:
    lane = get_lane(conn, lane_id)
    name = payload.name.strip() if payload.name is not None else lane.name
    status = (payload.status or lane.status).lower()
    if status not in VALID_LANE_STATUSES:
        raise ValueError("status must be active, paused, or archived")

    strategy_version = payload.strategy_version or lane.strategy_version
    plan_version = payload.plan_version or lane.plan_version
    if payload.strategy_version is not None:
        _validate_strategy_version(conn, strategy_version)
    if payload.plan_version is not None:
        _validate_plan_version(conn, plan_version)

    if lane.lane_role == "live" and status == "archived":
        raise ValueError("Cannot archive the active live lane; promote another lane first")

    conn.execute(
        """
        UPDATE simulation_lanes
        SET name = ?, status = ?, strategy_version = ?, plan_version = ?, updated_at = ?
        WHERE id = ?
        """,
        (name, status, strategy_version, plan_version, _iso_now(), lane_id),
    )
    return get_lane(conn, lane_id)


def reset_lane_portfolio(conn: sqlite3.Connection, lane_id: int) -> tuple[int, float]:
    lane = get_lane(conn, lane_id)
    positions_cleared = conn.execute(
        "SELECT COUNT(*) AS c FROM simulated_positions WHERE lane_id = ?",
        (lane_id,),
    ).fetchone()["c"]
    conn.execute("DELETE FROM simulated_positions WHERE lane_id = ?", (lane_id,))
    conn.execute(
        """
        INSERT INTO simulated_cash (lane_id, cash_usd, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(lane_id) DO UPDATE SET
            cash_usd = excluded.cash_usd,
            updated_at = excluded.updated_at
        """,
        (lane_id, lane.initial_cash_usd, _iso_now()),
    )
    conn.execute(
        "DELETE FROM symbol_memory_summaries WHERE lane_id = ?",
        (lane_id,),
    )
    return int(positions_cleared), lane.initial_cash_usd


def ensure_primary_lane(conn: sqlite3.Connection) -> int:
    """Create default primary lane from active strategy/plan if missing."""
    count = conn.execute("SELECT COUNT(*) AS c FROM simulation_lanes").fetchone()["c"]
    if count > 0:
        return get_primary_lane_id(conn)

    from app.safety import get_active_strategy
    from app.plan_service import get_active_plan_version

    try:
        strategy = get_active_strategy(conn)
    except RuntimeError:
        return PRIMARY_LANE_ID

    plan_version = get_active_plan_version(conn) or "v1"
    initial_cash = settings.initial_simulated_cash

    cash_row = conn.execute("SELECT cash_usd FROM simulated_cash WHERE lane_id = 1").fetchone()
    if cash_row is not None:
        initial_cash = float(cash_row["cash_usd"])

    now = _iso_now()
    conn.execute(
        """
        INSERT INTO simulation_lanes (
            id, name, strategy_version, plan_version, lane_role, status,
            initial_cash_usd, created_at, updated_at
        ) VALUES (1, 'primary', ?, ?, 'research', 'active', ?, ?, ?)
        """,
        (strategy.version, plan_version, initial_cash, now, now),
    )
    _ensure_lane_cash_row(conn, PRIMARY_LANE_ID, initial_cash)
    return PRIMARY_LANE_ID


def promote_lane_to_live(
    conn: sqlite3.Connection,
    lane_id: int,
    *,
    approved_by: str | None = None,
) -> LanePromoteResponse:
    from app.alert_service import dispatch_typed_alert
    from app.preflight_service import get_live_preflight
    from app.services import activate_strategy_as_live

    lane = get_lane(conn, lane_id)
    if lane.lane_role == "live":
        raise ValueError(f"Lane {lane_id} is already live")

    if lane.status != "active":
        raise ValueError(f"Lane {lane_id} must be active to promote")

    preflight = get_live_preflight(conn)
    if not preflight.ready_for_live:
        raise ValueError("Preflight checks failing — cannot promote lane to live")

    strategy = get_strategy_by_version(conn, lane.strategy_version)
    now = _iso_now()

    old_live = conn.execute(
        """
        SELECT id FROM simulation_lanes
        WHERE lane_role = 'live' AND status = 'active'
        """
    ).fetchone()
    if old_live is not None:
        conn.execute(
            """
            UPDATE simulation_lanes
            SET lane_role = 'shadow', updated_at = ?
            WHERE id = ?
            """,
            (now, old_live["id"]),
        )

    _close_open_live_periods(conn, now)

    conn.execute(
        """
        UPDATE simulation_lanes
        SET lane_role = 'live', updated_at = ?
        WHERE id = ?
        """,
        (now, lane_id),
    )

    _start_live_period(conn, lane_id, now)

    activate_strategy_as_live(conn, strategy)

    dispatch_typed_alert(
        conn,
        alert_type="live_lane_promoted",
        title=f"Live lane promoted: {lane.name}",
        message=(
            f"Lane #{lane_id} ({lane.strategy_version} + {lane.plan_version}) "
            f"is now the live deployment."
        ),
        entity_type="lane",
        entity_id=str(lane_id),
        payload={"lane_id": lane_id, "approved_by": approved_by},
        force=True,
    )

    updated = get_lane(conn, lane_id)
    return LanePromoteResponse(
        lane=updated,
        message=f"Lane {lane_id} promoted to live.",
        previous_live_lane_id=int(old_live["id"]) if old_live else None,
    )
