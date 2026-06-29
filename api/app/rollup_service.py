"""Daily rollup aggregation for long-term trends without full detail retention."""

import json
import sqlite3
from datetime import datetime, timezone

from app.schemas import DailyRollupOut, RollupRunOut

SIMULATED_ACTIONS = ("simulated_buy", "simulated_sell", "paper_buy", "paper_sell")
LIVE_ACTIONS = ("buy", "sell")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _day_key(iso_ts: str) -> str:
    return iso_ts[:10]


def compute_daily_rollup(conn: sqlite3.Connection, rollup_date: str) -> DailyRollupOut:
    day_start = f"{rollup_date} 00:00:00"
    day_end = f"{rollup_date} 23:59:59"

    run_stats = conn.execute(
        """
        SELECT COUNT(*) AS run_count,
               SUM(CASE WHEN lower(status) = 'completed' THEN 1 ELSE 0 END) AS completed_runs,
               SUM(CASE WHEN lower(status) = 'failed' THEN 1 ELSE 0 END) AS failed_runs
        FROM automation_runs
        WHERE run_at >= ? AND run_at <= ?
        """,
        (day_start, day_end),
    ).fetchone()

    decision_stats = conn.execute(
        """
        SELECT COUNT(*) AS decision_count,
               AVG(confidence) AS avg_confidence,
               SUM(CASE WHEN lower(action) IN ('simulated_buy','simulated_sell','paper_buy','paper_sell')
                   THEN 1 ELSE 0 END) AS simulated_trades,
               SUM(CASE WHEN lower(action) IN ('buy','sell') THEN 1 ELSE 0 END) AS live_trades,
               SUM(CASE WHEN lower(action) IN ('hold','skip','no_action') THEN 1 ELSE 0 END) AS passive_decisions
        FROM decisions
        WHERE created_at >= ? AND created_at <= ?
        """,
        (day_start, day_end),
    ).fetchone()

    cost_row = conn.execute(
        """
        SELECT COALESCE(SUM(cost_usd), 0) AS total_cost
        FROM cursor_usage
        WHERE reconciled_at >= ? AND reconciled_at <= ?
        """,
        (day_start, day_end),
    ).fetchone()

    alert_count = conn.execute(
        """
        SELECT COUNT(*) AS c FROM alerts
        WHERE created_at >= ? AND created_at <= ?
        """,
        (day_start, day_end),
    ).fetchone()["c"]

    equity = conn.execute(
        """
        SELECT total_equity_usd FROM portfolio_snapshots
        WHERE snapshot_at >= ? AND snapshot_at <= ?
        ORDER BY snapshot_at ASC
        """,
        (day_start, day_end),
    ).fetchall()
    equity_change = None
    if len(equity) >= 2:
        equity_change = round(float(equity[-1]["total_equity_usd"]) - float(equity[0]["total_equity_usd"]), 2)

    by_strategy = {
        row["strategy_version"]: row["c"]
        for row in conn.execute(
            """
            SELECT strategy_version, COUNT(*) AS c FROM automation_runs
            WHERE run_at >= ? AND run_at <= ? AND strategy_version IS NOT NULL
            GROUP BY strategy_version
            """,
            (day_start, day_end),
        )
    }

    return DailyRollupOut(
        rollup_date=rollup_date,
        run_count=int(run_stats["run_count"] or 0),
        completed_runs=int(run_stats["completed_runs"] or 0),
        failed_runs=int(run_stats["failed_runs"] or 0),
        decision_count=int(decision_stats["decision_count"] or 0),
        simulated_trades=int(decision_stats["simulated_trades"] or 0),
        live_trades=int(decision_stats["live_trades"] or 0),
        passive_decisions=int(decision_stats["passive_decisions"] or 0),
        avg_confidence=decision_stats["avg_confidence"],
        total_cost_usd=float(cost_row["total_cost"] or 0),
        alert_count=int(alert_count),
        equity_change_usd=equity_change,
        runs_by_strategy=by_strategy,
    )


def upsert_daily_rollup(conn: sqlite3.Connection, rollup_date: str) -> DailyRollupOut:
    rollup = compute_daily_rollup(conn, rollup_date)
    now = _iso_now()
    conn.execute(
        """
        INSERT INTO daily_rollups (
            rollup_date, run_count, completed_runs, failed_runs, decision_count,
            simulated_trades, live_trades, passive_decisions, avg_confidence,
            total_cost_usd, alert_count, equity_change_usd, runs_by_strategy_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rollup_date) DO UPDATE SET
            run_count = excluded.run_count,
            completed_runs = excluded.completed_runs,
            failed_runs = excluded.failed_runs,
            decision_count = excluded.decision_count,
            simulated_trades = excluded.simulated_trades,
            live_trades = excluded.live_trades,
            passive_decisions = excluded.passive_decisions,
            avg_confidence = excluded.avg_confidence,
            total_cost_usd = excluded.total_cost_usd,
            alert_count = excluded.alert_count,
            equity_change_usd = excluded.equity_change_usd,
            runs_by_strategy_json = excluded.runs_by_strategy_json,
            updated_at = excluded.updated_at
        """,
        (
            rollup.rollup_date,
            rollup.run_count,
            rollup.completed_runs,
            rollup.failed_runs,
            rollup.decision_count,
            rollup.simulated_trades,
            rollup.live_trades,
            rollup.passive_decisions,
            rollup.avg_confidence,
            rollup.total_cost_usd,
            rollup.alert_count,
            rollup.equity_change_usd,
            json.dumps(rollup.runs_by_strategy),
            now,
        ),
    )
    return rollup


def run_rollup_job(conn: sqlite3.Connection, *, days: int = 30) -> RollupRunOut:
    if days < 1:
        raise ValueError("days must be at least 1")
    rows = conn.execute(
        """
        SELECT DISTINCT date(run_at) AS d FROM automation_runs
        WHERE datetime(run_at) >= datetime('now', ?)
        UNION
        SELECT DISTINCT date(created_at) AS d FROM decisions
        WHERE datetime(created_at) >= datetime('now', ?)
        ORDER BY d DESC
        """,
        (f"-{days} days", f"-{days} days"),
    )
    dates = [row["d"] for row in rows if row["d"]]
    if not dates:
        today = datetime.now(timezone.utc).date().isoformat()
        dates = [today]
    upserted = 0
    for rollup_date in dates:
        upsert_daily_rollup(conn, rollup_date)
        upserted += 1
    return RollupRunOut(upserted_days=upserted, message=f"Rollups updated for {upserted} day(s).")


def list_daily_rollups(conn: sqlite3.Connection, limit: int = 90) -> list[DailyRollupOut]:
    rows = conn.execute(
        """
        SELECT rollup_date, run_count, completed_runs, failed_runs, decision_count,
               simulated_trades, live_trades, passive_decisions, avg_confidence,
               total_cost_usd, alert_count, equity_change_usd, runs_by_strategy_json
        FROM daily_rollups
        ORDER BY rollup_date DESC LIMIT ?
        """,
        (limit,),
    )
    results: list[DailyRollupOut] = []
    for row in rows:
        results.append(
            DailyRollupOut(
                rollup_date=row["rollup_date"],
                run_count=row["run_count"],
                completed_runs=row["completed_runs"],
                failed_runs=row["failed_runs"],
                decision_count=row["decision_count"],
                simulated_trades=row["simulated_trades"],
                live_trades=row["live_trades"],
                passive_decisions=row["passive_decisions"],
                avg_confidence=row["avg_confidence"],
                total_cost_usd=row["total_cost_usd"],
                alert_count=row["alert_count"],
                equity_change_usd=row["equity_change_usd"],
                runs_by_strategy=json.loads(row["runs_by_strategy_json"] or "{}"),
            )
        )
    return results
