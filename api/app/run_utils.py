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
        budget_exceeded=bool(row["budget_exceeded"]) if "budget_exceeded" in keys else False,
        expected_budget_usd=row["expected_budget_usd"] if "expected_budget_usd" in keys else None,
        actual_cost_usd=row["actual_cost_usd"] if "actual_cost_usd" in keys else None,
    )


RUN_SUMMARY_SELECT = """
    id, run_at, automation_name, run_type, market_summary, status,
    strategy_version, plan_version, mode, buying_power, cursor_run_id, created_at,
    budget_exceeded, expected_budget_usd, actual_cost_usd
"""
