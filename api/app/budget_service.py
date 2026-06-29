"""Per-run-type budget expectations and guardrail evaluation."""

import sqlite3
from datetime import datetime, timezone

from app.config import settings
from app.run_constants import DEFAULT_RUN_TYPE, VALID_RUN_TYPES
from app.schemas import RunBudgetCheckOut, UsageBudgetOut

RUN_TYPE_BUDGET_USD: dict[str, float] = {
    "daily_research": 0.75,
    "signal_response": 0.15,
    "post_market_review": 0.50,
    "reconciliation_only": 0.10,
    "live_preflight": 1.00,
}

RUN_TYPE_TOKEN_LIMITS: dict[str, int] = {
    "daily_research": 120_000,
    "signal_response": 30_000,
    "post_market_review": 80_000,
    "reconciliation_only": 20_000,
    "live_preflight": 150_000,
}


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _day_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def expected_budget_for_run_type(run_type: str | None) -> float:
    normalized = (run_type or DEFAULT_RUN_TYPE).lower().strip()
    if normalized not in VALID_RUN_TYPES:
        normalized = DEFAULT_RUN_TYPE
    return RUN_TYPE_BUDGET_USD.get(normalized, RUN_TYPE_BUDGET_USD[DEFAULT_RUN_TYPE])


def expected_tokens_for_run_type(run_type: str | None) -> int:
    normalized = (run_type or DEFAULT_RUN_TYPE).lower().strip()
    if normalized not in VALID_RUN_TYPES:
        normalized = DEFAULT_RUN_TYPE
    return RUN_TYPE_TOKEN_LIMITS.get(normalized, RUN_TYPE_TOKEN_LIMITS[DEFAULT_RUN_TYPE])


def get_usage_budget(conn: sqlite3.Connection) -> UsageBudgetOut:
    daily_spent = conn.execute(
        """
        SELECT COALESCE(SUM(cost_usd), 0) AS total
        FROM cursor_usage
        WHERE datetime(reconciled_at) >= datetime(?)
        """,
        (_day_start_iso(),),
    ).fetchone()["total"]

    monthly_spent = conn.execute(
        """
        SELECT COALESCE(SUM(cost_usd), 0) AS total
        FROM cursor_usage
        WHERE datetime(reconciled_at) >= datetime(?)
        """,
        (_month_start_iso(),),
    ).fetchone()["total"]

    daily_budget = settings.daily_budget_usd
    monthly_budget = settings.monthly_budget_usd
    daily_remaining = max(0.0, daily_budget - float(daily_spent or 0))
    monthly_remaining = max(0.0, monthly_budget - float(monthly_spent or 0))
    daily_exceeded = float(daily_spent or 0) > daily_budget
    monthly_exceeded = float(monthly_spent or 0) > monthly_budget

    return UsageBudgetOut(
        daily_budget_usd=daily_budget,
        monthly_budget_usd=monthly_budget,
        daily_spent_usd=round(float(daily_spent or 0), 4),
        monthly_spent_usd=round(float(monthly_spent or 0), 4),
        daily_remaining_usd=round(daily_remaining, 4),
        monthly_remaining_usd=round(monthly_remaining, 4),
        daily_exceeded=daily_exceeded,
        monthly_exceeded=monthly_exceeded,
        budget_ok=not daily_exceeded and not monthly_exceeded,
        run_type_budget_usd=dict(RUN_TYPE_BUDGET_USD),
        run_type_token_limits=dict(RUN_TYPE_TOKEN_LIMITS),
    )


def evaluate_run_budget(
    *,
    run_type: str | None,
    cost_usd: float | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> RunBudgetCheckOut:
    expected_usd = expected_budget_for_run_type(run_type)
    expected_tokens = expected_tokens_for_run_type(run_type)
    actual_cost = float(cost_usd or 0)
    total_tokens = (input_tokens or 0) + (output_tokens or 0)

    cost_exceeded = cost_usd is not None and actual_cost > expected_usd
    tokens_exceeded = total_tokens > 0 and total_tokens > expected_tokens
    exceeded = cost_exceeded or tokens_exceeded

    messages: list[str] = []
    if cost_exceeded:
        messages.append(
            f"Run cost ${actual_cost:.4f} exceeds {run_type or DEFAULT_RUN_TYPE} budget ${expected_usd:.2f}"
        )
    if tokens_exceeded:
        messages.append(
            f"Run tokens {total_tokens} exceed {run_type or DEFAULT_RUN_TYPE} limit {expected_tokens}"
        )

    return RunBudgetCheckOut(
        run_type=run_type or DEFAULT_RUN_TYPE,
        expected_budget_usd=expected_usd,
        actual_cost_usd=actual_cost if cost_usd is not None else None,
        expected_token_limit=expected_tokens,
        actual_tokens=total_tokens if total_tokens > 0 else None,
        budget_exceeded=exceeded,
        message="; ".join(messages) if messages else "Within run budget.",
    )
