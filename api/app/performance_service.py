import sqlite3

from app.schemas import StrategyPerformanceOut, StrategyPerformanceSliceOut


def get_strategy_performance(
    conn: sqlite3.Connection,
    *,
    strategy_version: str | None = None,
    since: str | None = None,
) -> StrategyPerformanceOut:
    run_clauses = ["1=1"]
    params: list[object] = []
    if strategy_version:
        run_clauses.append("strategy_version = ?")
        params.append(strategy_version)
    if since:
        run_clauses.append("run_at >= ?")
        params.append(since)
    run_where = " AND ".join(run_clauses)

    run_stats = conn.execute(
        f"""
        SELECT COUNT(*) AS run_count,
               SUM(CASE WHEN lower(status) = 'failed' THEN 1 ELSE 0 END) AS failed_runs
        FROM automation_runs
        WHERE {run_where}
        """,
        params,
    ).fetchone()
    run_count = int(run_stats["run_count"] or 0)

    decision_clauses = ["1=1"]
    decision_params: list[object] = []
    if strategy_version:
        decision_clauses.append(
            "run_id IN (SELECT id FROM automation_runs WHERE strategy_version = ?)"
        )
        decision_params.append(strategy_version)
    if since:
        decision_clauses.append("created_at >= ?")
        decision_params.append(since)
    decision_where = " AND ".join(decision_clauses)

    decision_stats = conn.execute(
        f"""
        SELECT COUNT(*) AS total,
               AVG(confidence) AS avg_confidence,
               SUM(CASE WHEN lower(action) IN (
                   'simulated_buy','simulated_sell','paper_buy','paper_sell'
               ) THEN 1 ELSE 0 END) AS simulated_trades,
               SUM(CASE WHEN lower(action) IN ('hold','skip','no_action') THEN 1 ELSE 0 END) AS passive
        FROM decisions
        WHERE {decision_where}
        """,
        decision_params,
    ).fetchone()

    by_action = [
        StrategyPerformanceSliceOut(
            key=row["action"],
            count=int(row["c"]),
            avg_confidence=row["avg_conf"],
        )
        for row in conn.execute(
            f"""
            SELECT lower(action) AS action, COUNT(*) AS c, AVG(confidence) AS avg_conf
            FROM decisions WHERE {decision_where}
            GROUP BY lower(action) ORDER BY c DESC
            """,
            decision_params,
        )
    ]

    equity_change = None
    snap_params: list[object] = []
    snap_where = "1=1"
    if since:
        snap_where = "snapshot_at >= ?"
        snap_params.append(since)
    snaps = conn.execute(
        f"""
        SELECT total_equity_usd FROM portfolio_snapshots
        WHERE {snap_where} ORDER BY snapshot_at ASC
        """,
        snap_params,
    ).fetchall()
    if len(snaps) >= 2:
        first_eq = float(snaps[0]["total_equity_usd"])
        last_eq = float(snaps[-1]["total_equity_usd"])
        equity_change = round(last_eq - first_eq, 2)

    versions = [
        row["strategy_version"]
        for row in conn.execute(
            """
            SELECT DISTINCT strategy_version FROM automation_runs
            WHERE strategy_version IS NOT NULL ORDER BY strategy_version
            """
        )
    ]

    return StrategyPerformanceOut(
        strategy_version=strategy_version,
        since=since,
        run_count=run_count,
        decision_count=int(decision_stats["total"] or 0),
        simulated_trades=int(decision_stats["simulated_trades"] or 0),
        passive_decisions=int(decision_stats["passive"] or 0),
        avg_confidence=decision_stats["avg_confidence"],
        equity_change_usd=equity_change,
        by_action=by_action,
        available_strategy_versions=versions,
    )
