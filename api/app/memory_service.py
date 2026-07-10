import json
from datetime import datetime, timezone

import sqlite3

from app.decision_utils import DECISION_SELECT_ALIASED, DECISION_SELECT_COLUMNS, decision_summary_from_row
from app.news_service import list_news_events
from app.integration_service import _get_quote_map, mark_position_with_quotes
from app.lane_service import get_strategy_for_lane, resolve_lane_id
from app.safety import BUY_ACTIONS, get_active_symbol_cooldowns

SELL_ACTIONS = {"sell", "place_sell", "simulated_sell", "paper_sell"}
from app.schemas import (
    ManualNoteOut,
    MarketSignalOut,
    SimulatedPositionOut,
    SymbolMemoryOut,
    SymbolMemorySummaryOut,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _position_for_symbol(
    conn: sqlite3.Connection,
    symbol: str,
    lane_id: int,
) -> SimulatedPositionOut | None:
    row = conn.execute(
        """
        SELECT symbol, quantity, avg_cost FROM simulated_positions
        WHERE lane_id = ? AND symbol = ?
        """,
        (lane_id, symbol.upper()),
    ).fetchone()
    if row is None:
        return None

    quote_map = _get_quote_map(conn)
    qty = float(row["quantity"])
    avg = float(row["avg_cost"])
    market_value, last_price, cost_basis, unrealized_pnl = mark_position_with_quotes(
        row["symbol"], qty, avg, quote_map
    )
    return SimulatedPositionOut(
        symbol=row["symbol"],
        quantity=qty,
        avg_cost=avg,
        last_price=last_price,
        market_value=market_value,
        cost_basis=cost_basis,
        unrealized_pnl=unrealized_pnl,
    )


def get_symbol_memory(
    conn: sqlite3.Connection,
    symbol: str,
    lane_id: int | None = None,
) -> SymbolMemoryOut:
    symbol = symbol.upper()
    resolved_lane = resolve_lane_id(conn, lane_id)
    strategy = get_strategy_for_lane(conn, resolved_lane)
    cooldowns = get_active_symbol_cooldowns(
        conn, strategy.rules.symbol_cooldown_hours, lane_id=resolved_lane
    )
    cooldown = cooldowns.get(symbol)

    summary_row = conn.execute(
        """
        SELECT symbol, last_action, last_buy_at, last_sell_at, last_run_id,
               trade_count, win_count, loss_count, realized_pnl_usd,
               unrealized_pnl_usd, risk_notes_json, updated_at
        FROM symbol_memory_summaries
        WHERE lane_id = ? AND symbol = ?
        """,
        (resolved_lane, symbol),
    ).fetchone()

    summary = None
    if summary_row is not None:
        risk_notes = (
            json.loads(summary_row["risk_notes_json"])
            if summary_row["risk_notes_json"]
            else []
        )
        summary = SymbolMemorySummaryOut(
            symbol=summary_row["symbol"],
            last_action=summary_row["last_action"],
            last_buy_at=summary_row["last_buy_at"],
            last_sell_at=summary_row["last_sell_at"],
            last_run_id=summary_row["last_run_id"],
            trade_count=int(summary_row["trade_count"]),
            win_count=int(summary_row["win_count"]),
            loss_count=int(summary_row["loss_count"]),
            realized_pnl_usd=float(summary_row["realized_pnl_usd"]),
            unrealized_pnl_usd=summary_row["unrealized_pnl_usd"],
            risk_notes=risk_notes,
            updated_at=summary_row["updated_at"],
        )

    decisions = [
        decision_summary_from_row(row)
        for row in conn.execute(
            f"""
            SELECT {DECISION_SELECT_ALIASED}
            FROM decisions d
            JOIN automation_runs r ON r.id = d.run_id
            WHERE r.lane_id = ? AND upper(d.symbol) = ?
            ORDER BY d.id DESC
            LIMIT 20
            """,
            (resolved_lane, symbol),
        )
    ]

    notes = [
        ManualNoteOut(id=row["id"], content=row["content"], created_at=row["created_at"])
        for row in conn.execute(
            """
            SELECT id, content, created_at
            FROM manual_notes
            WHERE active = 1 AND upper(content) LIKE '%' || upper(?) || '%'
            ORDER BY id DESC
            LIMIT 5
            """,
            (symbol,),
        )
    ]

    signals = [
        MarketSignalOut(
            id=row["id"],
            signal_type=row["signal_type"],
            symbol=row["symbol"],
            message=row["message"],
            source=row["source"],
            created_at=row["created_at"],
        )
        for row in conn.execute(
            """
            SELECT id, signal_type, symbol, message, source, created_at
            FROM market_signals
            WHERE upper(symbol) = upper(?)
            ORDER BY id DESC
            LIMIT 10
            """,
            (symbol,),
        )
    ]

    position = _position_for_symbol(conn, symbol, resolved_lane)
    cash_row = conn.execute(
        "SELECT cash_usd FROM simulated_cash WHERE lane_id = ?",
        (resolved_lane,),
    ).fetchone()
    cash = float(cash_row["cash_usd"]) if cash_row else 0.0
    position_value = position.market_value if position else 0.0
    portfolio_total_equity = cash + position_value
    recent_news = list_news_events(conn, symbol=symbol, limit=10)

    return SymbolMemoryOut(
        symbol=symbol,
        lane_id=resolved_lane,
        summary=summary,
        cooldown=cooldown,
        position=position,
        portfolio_total_equity=portfolio_total_equity,
        recent_decisions=decisions,
        related_notes=notes,
        recent_signals=signals,
        recent_news=recent_news,
    )


def update_symbol_memory_for_decision(
    conn: sqlite3.Connection,
    *,
    lane_id: int,
    run_id: int,
    symbol: str,
    action: str,
    created_at: str | None = None,
) -> None:
    symbol = symbol.upper()
    action = action.lower()
    now = created_at or _iso_now()

    row = conn.execute(
        """
        SELECT symbol FROM symbol_memory_summaries
        WHERE lane_id = ? AND symbol = ?
        """,
        (lane_id, symbol),
    ).fetchone()

    if row is None:
        conn.execute(
            """
            INSERT INTO symbol_memory_summaries (
                lane_id, symbol, last_action, last_run_id, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (lane_id, symbol, action, run_id, now),
        )
    else:
        conn.execute(
            """
            UPDATE symbol_memory_summaries
            SET last_action = ?, last_run_id = ?, updated_at = ?
            WHERE lane_id = ? AND symbol = ?
            """,
            (action, run_id, now, lane_id, symbol),
        )

    if action in BUY_ACTIONS:
        conn.execute(
            """
            UPDATE symbol_memory_summaries
            SET last_buy_at = ?, trade_count = trade_count + 1
            WHERE lane_id = ? AND symbol = ?
            """,
            (now, lane_id, symbol),
        )
    elif action in SELL_ACTIONS:
        conn.execute(
            """
            UPDATE symbol_memory_summaries
            SET last_sell_at = ?, trade_count = trade_count + 1
            WHERE lane_id = ? AND symbol = ?
            """,
            (now, lane_id, symbol),
        )

    position = _position_for_symbol(conn, symbol, lane_id)
    if position and position.unrealized_pnl is not None:
        conn.execute(
            """
            UPDATE symbol_memory_summaries
            SET unrealized_pnl_usd = ?
            WHERE lane_id = ? AND symbol = ?
            """,
            (position.unrealized_pnl, lane_id, symbol),
        )


def backfill_symbol_memory_summaries(conn: sqlite3.Connection, lane_id: int = 1) -> int:
    symbols = conn.execute(
        """
        SELECT DISTINCT upper(d.symbol) AS symbol
        FROM decisions d
        JOIN automation_runs r ON r.id = d.run_id
        WHERE r.lane_id = ?
        ORDER BY symbol
        """,
        (lane_id,),
    ).fetchall()
    count = 0
    for row in symbols:
        symbol = row["symbol"]
        latest = conn.execute(
            """
            SELECT d.run_id, d.action, d.created_at
            FROM decisions d
            JOIN automation_runs r ON r.id = d.run_id
            WHERE r.lane_id = ? AND upper(d.symbol) = ?
            ORDER BY d.id DESC
            LIMIT 1
            """,
            (lane_id, symbol),
        ).fetchone()
        if latest is None:
            continue
        update_symbol_memory_for_decision(
            conn,
            lane_id=lane_id,
            run_id=latest["run_id"],
            symbol=symbol,
            action=latest["action"],
            created_at=latest["created_at"],
        )
        count += 1
    return count
