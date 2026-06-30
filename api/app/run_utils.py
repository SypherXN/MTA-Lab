import sqlite3

from app.schemas import RunSummaryOut


def run_summary_from_row(row: sqlite3.Row) -> RunSummaryOut:
    keys = row.keys()
    return RunSummaryOut(
        id=row["id"],
        run_at=row["run_at"],
        automation_name=row["automation_name"],
        run_type=row["run_type"] if "run_type" in keys else None,
        market_summary=row["market_summary"],
        status=row["status"],
        strategy_version=row["strategy_version"],
        plan_version=row["plan_version"] if "plan_version" in keys else None,
        mode=row["mode"],
        buying_power=row["buying_power"],
        cursor_run_id=row["cursor_run_id"],
        created_at=row["created_at"],
        lane_id=row["lane_id"] if "lane_id" in keys else None,
        lane_name=row["lane_name"] if "lane_name" in keys else None,
        lane_role=row["lane_role"] if "lane_role" in keys else None,
        budget_exceeded=bool(row["budget_exceeded"]) if "budget_exceeded" in keys else False,
        expected_budget_usd=row["expected_budget_usd"] if "expected_budget_usd" in keys else None,
        actual_cost_usd=row["actual_cost_usd"] if "actual_cost_usd" in keys else None,
    )


RUN_SUMMARY_SELECT = """
    r.id, r.run_at, r.automation_name, r.run_type, r.market_summary, r.status,
    r.strategy_version, r.plan_version, r.mode, r.buying_power, r.cursor_run_id, r.created_at,
    r.budget_exceeded, r.expected_budget_usd, r.actual_cost_usd, r.lane_id,
    l.name AS lane_name, l.lane_role AS lane_role
"""

RUN_SUMMARY_FROM = """
    automation_runs r
    LEFT JOIN simulation_lanes l ON l.id = r.lane_id
"""
