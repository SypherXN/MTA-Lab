from datetime import datetime, timezone

import sqlite3


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_portfolio_snapshot(
    conn: sqlite3.Connection,
    *,
    run_id: int | None = None,
    source: str = "run",
    snapshot_at: str | None = None,
    cash_usd: float,
    total_equity: float,
    unrealized_pnl: float | None,
) -> int:
    positions_value = total_equity - cash_usd
    cursor = conn.execute(
        """
        INSERT INTO portfolio_snapshots (
            snapshot_at, run_id, cash_usd, positions_value_usd,
            total_equity_usd, unrealized_pnl_usd, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_at or _iso_now(),
            run_id,
            cash_usd,
            positions_value,
            total_equity,
            unrealized_pnl,
            source,
        ),
    )
    return int(cursor.lastrowid)


def get_portfolio_snapshots(
    conn: sqlite3.Connection,
    *,
    limit: int = 100,
    since: str | None = None,
    until: str | None = None,
    run_id: int | None = None,
) -> list[sqlite3.Row]:
    query = """
        SELECT id, snapshot_at, run_id, cash_usd, positions_value_usd,
               total_equity_usd, unrealized_pnl_usd, source, created_at
        FROM portfolio_snapshots
        WHERE 1=1
    """
    params: list = []
    if since:
        query += " AND snapshot_at >= ?"
        params.append(since)
    if until:
        query += " AND snapshot_at <= ?"
        params.append(until)
    if run_id is not None:
        query += " AND run_id = ?"
        params.append(run_id)
    query += " ORDER BY snapshot_at ASC, id ASC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def get_portfolio_snapshot_summary(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS snapshot_count,
            MIN(snapshot_at) AS first_snapshot_at,
            MAX(snapshot_at) AS last_snapshot_at,
            MIN(total_equity_usd) AS min_equity_usd,
            MAX(total_equity_usd) AS max_equity_usd
        FROM portfolio_snapshots
        """
    ).fetchone()
    if row is None or row["snapshot_count"] == 0:
        return None

    first = conn.execute(
        """
        SELECT total_equity_usd, snapshot_at
        FROM portfolio_snapshots
        ORDER BY snapshot_at ASC, id ASC
        LIMIT 1
        """
    ).fetchone()
    last = conn.execute(
        """
        SELECT total_equity_usd, snapshot_at, run_id, unrealized_pnl_usd
        FROM portfolio_snapshots
        ORDER BY snapshot_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()

    first_equity = float(first["total_equity_usd"])
    last_equity = float(last["total_equity_usd"])
    change_usd = last_equity - first_equity
    change_pct = (change_usd / first_equity * 100) if first_equity else 0.0

    return {
        "snapshot_count": int(row["snapshot_count"]),
        "first_snapshot_at": first["snapshot_at"],
        "last_snapshot_at": last["snapshot_at"],
        "first_equity_usd": first_equity,
        "last_equity_usd": last_equity,
        "min_equity_usd": float(row["min_equity_usd"]),
        "max_equity_usd": float(row["max_equity_usd"]),
        "change_usd": change_usd,
        "change_pct": change_pct,
        "last_run_id": last["run_id"],
        "last_unrealized_pnl_usd": last["unrealized_pnl_usd"],
    }
