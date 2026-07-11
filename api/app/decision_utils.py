"""Map decision DB rows to API models."""

import sqlite3

from app.schemas import DecisionDetailOut, DecisionScoresOut, DecisionSummaryOut

DECISION_SELECT_COLUMNS = """
    id, run_id, symbol, action, reason, confidence, technical_score, news_score,
    risk_score, action_rationale, review_output, mode, amount_usd, created_at, order_id
"""

DECISION_SELECT_ALIASED = """
    d.id, d.run_id, d.symbol, d.action, d.reason, d.confidence, d.technical_score, d.news_score,
    d.risk_score, d.action_rationale, d.review_output, d.mode, d.amount_usd, d.created_at, d.order_id
"""

DECISION_DASHBOARD_SELECT = f"""
    {DECISION_SELECT_ALIASED.strip()},
    r.lane_id, l.name AS lane_name, l.lane_role AS lane_role
"""

DECISION_DASHBOARD_FROM = """
    decisions d
    LEFT JOIN automation_runs r ON r.id = d.run_id
    LEFT JOIN simulation_lanes l ON l.id = r.lane_id
"""


def scores_from_row(row: sqlite3.Row) -> DecisionScoresOut | None:
    technical = row["technical_score"]
    news = row["news_score"]
    risk = row["risk_score"]
    if technical is None and news is None and risk is None:
        return None
    return DecisionScoresOut(
        technical=technical,
        news=news,
        risk=risk,
        confidence=row["confidence"],
    )


def decision_summary_from_row(row: sqlite3.Row) -> DecisionSummaryOut:
    keys = row.keys()
    return DecisionSummaryOut(
        id=row["id"],
        run_id=row["run_id"],
        symbol=row["symbol"],
        action=row["action"],
        reason=row["reason"],
        confidence=row["confidence"],
        scores=scores_from_row(row),
        action_rationale=row["action_rationale"],
        review_output=row["review_output"],
        mode=row["mode"],
        amount_usd=row["amount_usd"],
        created_at=row["created_at"],
        lane_id=row["lane_id"] if "lane_id" in keys else None,
        lane_name=row["lane_name"] if "lane_name" in keys else None,
        lane_role=row["lane_role"] if "lane_role" in keys else None,
    )


def decision_detail_from_row(row: sqlite3.Row) -> DecisionDetailOut:
    return DecisionDetailOut(
        id=row["id"],
        run_id=row["run_id"],
        symbol=row["symbol"],
        action=row["action"],
        reason=row["reason"],
        confidence=row["confidence"],
        scores=scores_from_row(row),
        action_rationale=row["action_rationale"],
        review_output=row["review_output"],
        mode=row["mode"],
        amount_usd=row["amount_usd"],
        created_at=row["created_at"],
        order_id=row["order_id"],
    )
