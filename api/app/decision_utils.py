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
