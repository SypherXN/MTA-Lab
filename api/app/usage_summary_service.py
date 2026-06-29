import sqlite3

from app.schemas import (
    UsageBreakdownOut,
    UsageDayOut,
    UsageSummaryOut,
)


def get_usage_summary(conn: sqlite3.Connection) -> UsageSummaryOut:
    total_cost = float(
        conn.execute("SELECT COALESCE(SUM(cost_usd), 0) AS t FROM cursor_usage").fetchone()["t"]
    )
    total_rows = conn.execute("SELECT COUNT(*) AS c FROM cursor_usage").fetchone()["c"]
    total_decisions = conn.execute("SELECT COUNT(*) AS c FROM decisions").fetchone()["c"]
    cost_per_decision = (
        round(total_cost / total_decisions, 4) if total_decisions > 0 else None
    )

    by_day = [
        UsageDayOut(
            day=row["day"],
            cost_usd=float(row["cost_usd"] or 0),
            row_count=int(row["row_count"]),
        )
        for row in conn.execute(
            """
            SELECT date(reconciled_at) AS day,
                   SUM(cost_usd) AS cost_usd,
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
            """
            SELECT COALESCE(model, 'unknown') AS key,
                   SUM(cost_usd) AS cost_usd,
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
            """
            SELECT COALESCE(r.run_type, 'unlinked') AS key,
                   SUM(u.cost_usd) AS cost_usd,
                   COUNT(*) AS row_count
            FROM cursor_usage u
            LEFT JOIN automation_runs r ON r.id = u.run_id
            GROUP BY COALESCE(r.run_type, 'unlinked')
            ORDER BY cost_usd DESC
            """
        )
    ]

    return UsageSummaryOut(
        total_cost_usd=total_cost,
        usage_row_count=int(total_rows),
        total_decisions=total_decisions,
        cost_per_decision=cost_per_decision,
        by_day=list(reversed(by_day)),
        by_model=by_model,
        by_run_type=by_run_type,
    )
