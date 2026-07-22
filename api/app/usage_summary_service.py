import sqlite3

from app.dashboard_service import EFFECTIVE_COST_SQL
from app.schemas import (
    UsageBreakdownOut,
    UsageDayOut,
    UsageSummaryOut,
)


def get_usage_summary(conn: sqlite3.Connection) -> UsageSummaryOut:
    total_billed = float(
        conn.execute("SELECT COALESCE(SUM(cost_usd), 0) AS t FROM cursor_usage").fetchone()["t"]
    )
    total_estimated = float(
        conn.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) AS t FROM cursor_usage"
        ).fetchone()["t"]
    )
    total_effective = float(
        conn.execute(
            f"SELECT COALESCE(SUM({EFFECTIVE_COST_SQL}), 0) AS t FROM cursor_usage"
        ).fetchone()["t"]
    )
    total_rows = conn.execute("SELECT COUNT(*) AS c FROM cursor_usage").fetchone()["c"]
    total_decisions = conn.execute("SELECT COUNT(*) AS c FROM decisions").fetchone()["c"]
    cost_per_decision = (
        round(total_billed / total_decisions, 4) if total_decisions > 0 else None
    )
    estimated_cost_per_decision = (
        round(total_effective / total_decisions, 4) if total_decisions > 0 else None
    )

    by_day = [
        UsageDayOut(
            day=row["day"],
            cost_usd=float(row["cost_usd"] or 0),
            row_count=int(row["row_count"]),
        )
        for row in conn.execute(
            f"""
            SELECT date(reconciled_at) AS day,
                   SUM({EFFECTIVE_COST_SQL}) AS cost_usd,
                   COUNT(*) AS row_count
            FROM cursor_usage
            GROUP BY date(reconciled_at)
            ORDER BY day DESC
            LIMIT 60
            """
        )
    ]

    by_model = [
        UsageBreakdownOut(
            key=row["key"] or "unknown",
            cost_usd=float(row["cost_usd"] or 0),
            row_count=int(row["row_count"]),
        )
        for row in conn.execute(
            f"""
            SELECT COALESCE(model, 'unknown') AS key,
                   SUM({EFFECTIVE_COST_SQL}) AS cost_usd,
                   COUNT(*) AS row_count
            FROM cursor_usage
            GROUP BY COALESCE(model, 'unknown')
            ORDER BY cost_usd DESC
            LIMIT 20
            """
        )
    ]

    by_run_type = [
        UsageBreakdownOut(
            key=row["key"] or "unlinked",
            cost_usd=float(row["cost_usd"] or 0),
            row_count=int(row["row_count"]),
        )
        for row in conn.execute(
            f"""
            SELECT COALESCE(r.run_type, 'unlinked') AS key,
                   SUM({EFFECTIVE_COST_SQL}) AS cost_usd,
                   COUNT(*) AS row_count
            FROM cursor_usage u
            LEFT JOIN automation_runs r ON r.id = u.run_id
            GROUP BY COALESCE(r.run_type, 'unlinked')
            ORDER BY cost_usd DESC
            """
        )
    ]

    return UsageSummaryOut(
        total_cost_usd=total_billed,
        total_estimated_cost_usd=total_estimated,
        total_effective_cost_usd=total_effective,
        usage_row_count=int(total_rows),
        total_decisions=total_decisions,
        cost_per_decision=cost_per_decision,
        estimated_cost_per_decision=estimated_cost_per_decision,
        by_day=list(reversed(by_day)),
        by_model=by_model,
        by_run_type=by_run_type,
    )
