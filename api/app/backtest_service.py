"""Simple backtest replay against historical decisions."""

import sqlite3

from app.schemas import BacktestReplayOut, BacktestReplayRowOut


def replay_decisions(
    conn: sqlite3.Connection,
    *,
    strategy_version: str | None = None,
    since: str | None = None,
    alternate_max_order_usd: float | None = None,
    require_min_confidence: float | None = None,
) -> BacktestReplayOut:
    clauses = ["1=1"]
    params: list[object] = []
    if strategy_version:
        clauses.append(
            "d.run_id IN (SELECT id FROM automation_runs WHERE strategy_version = ?)"
        )
        params.append(strategy_version)
    if since:
        clauses.append("d.created_at >= ?")
        params.append(since)
    where = " AND ".join(clauses)

    rows = conn.execute(
        f"""
        SELECT d.id, d.run_id, d.symbol, d.action, d.confidence, d.amount_usd,
               d.reason, r.strategy_version, r.run_at
        FROM decisions d
        JOIN automation_runs r ON r.id = d.run_id
        WHERE {where}
        ORDER BY d.id ASC
        """,
        params,
    )

    replay_rows: list[BacktestReplayRowOut] = []
    would_change = 0
    blocked_by_alt = 0

    for row in rows:
        action = row["action"].lower()
        confidence = row["confidence"]
        amount = row["amount_usd"]
        alt_action = action
        changed = False
        blocked = False

        if require_min_confidence is not None and confidence is not None:
            if confidence < require_min_confidence and action in (
                "simulated_buy",
                "simulated_sell",
                "buy",
                "sell",
            ):
                alt_action = "hold"
                changed = True

        if alternate_max_order_usd is not None and amount is not None:
            if amount > alternate_max_order_usd and "buy" in action:
                alt_action = "hold"
                blocked = True
                changed = True

        if changed:
            would_change += 1
        if blocked:
            blocked_by_alt += 1

        replay_rows.append(
            BacktestReplayRowOut(
                decision_id=row["id"],
                run_id=row["run_id"],
                run_at=row["run_at"],
                strategy_version=row["strategy_version"],
                symbol=row["symbol"],
                original_action=action,
                alternate_action=alt_action,
                confidence=confidence,
                amount_usd=amount,
                changed=changed,
                reason=row["reason"],
            )
        )

    return BacktestReplayOut(
        strategy_version=strategy_version,
        since=since,
        alternate_max_order_usd=alternate_max_order_usd,
        require_min_confidence=require_min_confidence,
        total_decisions=len(replay_rows),
        would_change_count=would_change,
        blocked_by_cap_count=blocked_by_alt,
        rows=replay_rows[:500],
    )
