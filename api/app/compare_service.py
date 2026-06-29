"""Strategy and plan version comparison aggregates."""

import sqlite3

from app.performance_service import get_strategy_performance
from app.schemas import StrategyCompareOut, StrategyCompareVersionOut


def compare_strategy_versions(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
) -> StrategyCompareOut:
    versions = [
        row["strategy_version"]
        for row in conn.execute(
            """
            SELECT DISTINCT strategy_version FROM automation_runs
            WHERE strategy_version IS NOT NULL
            ORDER BY strategy_version
            """
        )
    ]
    plan_versions = [
        row["plan_version"]
        for row in conn.execute(
            """
            SELECT DISTINCT plan_version FROM automation_runs
            WHERE plan_version IS NOT NULL
            ORDER BY plan_version
            """
        )
    ]

    by_strategy: list[StrategyCompareVersionOut] = []
    for version in versions:
        perf = get_strategy_performance(conn, strategy_version=version, since=since)
        cost = conn.execute(
            """
            SELECT COALESCE(SUM(cu.cost_usd), 0) AS total
            FROM cursor_usage cu
            JOIN automation_runs r ON r.id = cu.run_id
            WHERE r.strategy_version = ?
            """,
            (version,),
        ).fetchone()["total"]
        by_strategy.append(
            StrategyCompareVersionOut(
                key=version,
                kind="strategy",
                run_count=perf.run_count,
                decision_count=perf.decision_count,
                simulated_trades=perf.simulated_trades,
                avg_confidence=perf.avg_confidence,
                equity_change_usd=perf.equity_change_usd,
                total_cost_usd=float(cost or 0),
            )
        )

    by_plan: list[StrategyCompareVersionOut] = []
    for version in plan_versions:
        run_count = conn.execute(
            "SELECT COUNT(*) AS c FROM automation_runs WHERE plan_version = ?",
            (version,),
        ).fetchone()["c"]
        decision_count = conn.execute(
            """
            SELECT COUNT(*) AS c FROM decisions d
            JOIN automation_runs r ON r.id = d.run_id
            WHERE r.plan_version = ?
            """,
            (version,),
        ).fetchone()["c"]
        avg_conf = conn.execute(
            """
            SELECT AVG(d.confidence) AS avg_c FROM decisions d
            JOIN automation_runs r ON r.id = d.run_id
            WHERE r.plan_version = ?
            """,
            (version,),
        ).fetchone()["avg_c"]
        by_plan.append(
            StrategyCompareVersionOut(
                key=version,
                kind="plan",
                run_count=int(run_count),
                decision_count=int(decision_count),
                simulated_trades=0,
                avg_confidence=avg_conf,
                equity_change_usd=None,
                total_cost_usd=0,
            )
        )

    return StrategyCompareOut(
        since=since,
        strategy_versions=by_strategy,
        plan_versions=by_plan,
    )
