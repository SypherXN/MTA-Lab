"""Sequential lane execution — one automation lane at a time."""

from datetime import datetime, timedelta, timezone

import sqlite3

from app.config import settings
from app.lane_service import get_lane, list_lanes
from app.schemas import LaneTurnOut

LOCK_ROW_ID = 1


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _expire_stale_lock(conn: sqlite3.Connection, now: str | None = None) -> None:
    now = now or _iso_now()
    conn.execute(
        """
        DELETE FROM lane_execution_lock
        WHERE expires_at <= ?
        """,
        (now,),
    )


def _get_lock(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT holder_lane_id, acquired_at, expires_at
        FROM lane_execution_lock
        WHERE id = ?
        """,
        (LOCK_ROW_ID,),
    ).fetchone()


def pick_next_lane_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        """
        SELECT l.id
        FROM simulation_lanes l
        LEFT JOIN (
            SELECT lane_id, MAX(run_at) AS last_run_at
            FROM automation_runs
            GROUP BY lane_id
        ) r ON r.lane_id = l.id
        WHERE l.status = 'active'
        ORDER BY COALESCE(r.last_run_at, '1970-01-01') ASC, l.id ASC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def _retry_after_seconds(expires_at: str) -> int:
    try:
        remaining = (_parse_iso(expires_at) - datetime.now(timezone.utc)).total_seconds()
    except ValueError:
        return settings.lane_lock_ttl_minutes * 60
    return max(int(remaining), 0)


def get_lane_turn(conn: sqlite3.Connection, lane_id: int, *, acquire: bool = False) -> LaneTurnOut:
    if not settings.sequential_lanes:
        return LaneTurnOut(
            sequential_mode=False,
            granted=True,
            lane_id=lane_id,
            message="Sequential lane mode is disabled.",
        )

    get_lane(conn, lane_id)
    now = _iso_now()
    _expire_stale_lock(conn, now)
    next_lane_id = pick_next_lane_id(conn)
    lock = _get_lock(conn)

    if lock is not None:
        holder_lane_id = int(lock["holder_lane_id"])
        if holder_lane_id == lane_id:
            if acquire:
                ttl = settings.lane_lock_ttl_minutes
                expires_at = (
                    datetime.now(timezone.utc) + timedelta(minutes=ttl)
                ).isoformat()
                conn.execute(
                    """
                    UPDATE lane_execution_lock
                    SET acquired_at = ?, expires_at = ?
                    WHERE id = ?
                    """,
                    (now, expires_at, LOCK_ROW_ID),
                )
            return LaneTurnOut(
                sequential_mode=True,
                granted=True,
                lane_id=lane_id,
                holder_lane_id=holder_lane_id,
                holder_since=lock["acquired_at"],
                next_lane_id=next_lane_id,
                message=f"Lane {lane_id} holds the execution turn.",
            )

        return LaneTurnOut(
            sequential_mode=True,
            granted=False,
            lane_id=lane_id,
            holder_lane_id=holder_lane_id,
            holder_since=lock["acquired_at"],
            next_lane_id=next_lane_id,
            retry_after_seconds=_retry_after_seconds(lock["expires_at"]),
            message=(
                f"Sequential mode: lane {holder_lane_id} is running. "
                f"Lane {lane_id} must wait."
            ),
        )

    if next_lane_id is None:
        return LaneTurnOut(
            sequential_mode=True,
            granted=False,
            lane_id=lane_id,
            message="No active lanes available for execution.",
        )

    if lane_id != next_lane_id:
        return LaneTurnOut(
            sequential_mode=True,
            granted=False,
            lane_id=lane_id,
            next_lane_id=next_lane_id,
            message=(
                f"Sequential mode: lane {next_lane_id} is due next "
                f"(oldest last run). Lane {lane_id} should skip this cycle."
            ),
        )

    if not acquire:
        return LaneTurnOut(
            sequential_mode=True,
            granted=True,
            lane_id=lane_id,
            next_lane_id=next_lane_id,
            message=f"Lane {lane_id} may run (due next, lock not yet acquired).",
        )

    ttl = settings.lane_lock_ttl_minutes
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ttl)).isoformat()
    conn.execute(
        """
        INSERT INTO lane_execution_lock (id, holder_lane_id, acquired_at, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            holder_lane_id = excluded.holder_lane_id,
            acquired_at = excluded.acquired_at,
            expires_at = excluded.expires_at
        """,
        (LOCK_ROW_ID, lane_id, now, expires_at),
    )
    return LaneTurnOut(
        sequential_mode=True,
        granted=True,
        lane_id=lane_id,
        holder_lane_id=lane_id,
        holder_since=now,
        next_lane_id=next_lane_id,
        message=f"Lane {lane_id} acquired the execution turn.",
    )


def verify_lane_turn_holder(conn: sqlite3.Connection, lane_id: int) -> None:
    if not settings.sequential_lanes:
        return

    now = _iso_now()
    _expire_stale_lock(conn, now)
    lock = _get_lock(conn)
    if lock is None:
        raise ValueError(
            f"Sequential mode: lane {lane_id} must call GET /context (or /lanes/turn) "
            "to acquire the execution turn before POST /runs."
        )
    if int(lock["holder_lane_id"]) != lane_id:
        raise ValueError(
            f"Sequential mode: lane {int(lock['holder_lane_id'])} holds the execution turn; "
            f"lane {lane_id} cannot post a run."
        )


def release_lane_turn(conn: sqlite3.Connection, lane_id: int) -> None:
    if not settings.sequential_lanes:
        return

    conn.execute(
        """
        DELETE FROM lane_execution_lock
        WHERE id = ? AND holder_lane_id = ?
        """,
        (LOCK_ROW_ID, lane_id),
    )
