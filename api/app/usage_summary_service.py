import calendar
import sqlite3
from datetime import datetime, timedelta, timezone

from app.dashboard_service import EFFECTIVE_COST_SQL
from app.schemas import (
    UsageBreakdownOut,
    UsageDayOut,
    UsagePeriodOut,
    UsageProjectionsOut,
    UsageSummaryOut,
)


def _iso_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_start(dt: datetime) -> datetime:
    return _day_start(dt) - timedelta(days=dt.weekday())


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _period_stats(conn: sqlite3.Connection, since_iso: str) -> UsagePeriodOut:
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM({EFFECTIVE_COST_SQL}), 0) AS cost_usd,
               COUNT(*) AS row_count,
               COUNT(DISTINCT run_id) AS run_count,
               COUNT(DISTINCT date(reconciled_at)) AS days_with_data
        FROM cursor_usage
        WHERE datetime(reconciled_at) >= datetime(?)
        """,
        (since_iso,),
    ).fetchone()
    cost = float(row["cost_usd"] or 0)
    row_count = int(row["row_count"] or 0)
    run_count = int(row["run_count"] or 0)
    days_with_data = int(row["days_with_data"] or 0)
    avg_per_day = round(cost / days_with_data, 4) if days_with_data > 0 else None
    cost_per_run = round(cost / run_count, 4) if run_count > 0 else None
    return UsagePeriodOut(
        cost_usd=round(cost, 4),
        row_count=row_count,
        run_count=run_count,
        days_with_data=days_with_data,
        avg_per_day_usd=avg_per_day,
        cost_per_run_usd=cost_per_run,
    )


def _build_projections(
    conn: sqlite3.Connection,
    last_7_days: UsagePeriodOut,
) -> UsageProjectionsOut | None:
    if last_7_days.days_with_data == 0:
        return None

    avg_daily = last_7_days.cost_usd / last_7_days.days_with_data
    now = _iso_now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    active_lane_count = int(
        conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM simulation_lanes
            WHERE status = 'active'
            """
        ).fetchone()["c"]
    )
    projected_weekly = avg_daily * 7
    projected_monthly = avg_daily * days_in_month
    per_lane = (
        round(projected_weekly / active_lane_count, 4) if active_lane_count > 0 else None
    )
    return UsageProjectionsOut(
        avg_daily_usd=round(avg_daily, 4),
        projected_weekly_usd=round(projected_weekly, 4),
        projected_monthly_usd=round(projected_monthly, 4),
        active_lane_count=active_lane_count,
        projected_weekly_per_lane_usd=per_lane,
    )


def _breakdown_query(group_expr: str, join_sql: str = "") -> str:
    return f"""
        SELECT {group_expr} AS key,
               SUM({EFFECTIVE_COST_SQL}) AS cost_usd,
               COUNT(*) AS row_count
        FROM cursor_usage u
        {join_sql}
        GROUP BY {group_expr}
        ORDER BY cost_usd DESC
        """


def get_usage_summary(conn: sqlite3.Connection) -> UsageSummaryOut:
    now = _iso_now()
    last_7_days = _period_stats(conn, (now - timedelta(days=7)).isoformat())
    last_30_days = _period_stats(conn, (now - timedelta(days=30)).isoformat())
    this_week = _period_stats(conn, _week_start(now).isoformat())
    this_month = _period_stats(conn, _month_start(now).isoformat())
    projections = _build_projections(conn, last_7_days)

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
        for row in conn.execute(_breakdown_query("COALESCE(model, 'unknown')"))
    ]

    by_run_type = [
        UsageBreakdownOut(
            key=row["key"] or "unlinked",
            cost_usd=float(row["cost_usd"] or 0),
            row_count=int(row["row_count"]),
        )
        for row in conn.execute(
            _breakdown_query(
                "COALESCE(r.run_type, 'unlinked')",
                "LEFT JOIN automation_runs r ON r.id = u.run_id",
            )
        )
    ]

    by_lane = [
        UsageBreakdownOut(
            key=row["key"] or "unlinked",
            cost_usd=float(row["cost_usd"] or 0),
            row_count=int(row["row_count"]),
        )
        for row in conn.execute(
            _breakdown_query(
                "COALESCE(l.name, 'unlinked')",
                """
                LEFT JOIN automation_runs r ON r.id = u.run_id
                LEFT JOIN simulation_lanes l ON l.id = r.lane_id
                """,
            )
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
        last_7_days=last_7_days,
        last_30_days=last_30_days,
        this_week=this_week,
        this_month=this_month,
        projections=projections,
        by_day=list(reversed(by_day)),
        by_model=by_model,
        by_run_type=by_run_type,
        by_lane=by_lane,
    )
