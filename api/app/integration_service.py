import json
from datetime import datetime, timezone

import sqlite3

from app.schemas import (
    MarketSignalOut,
    PriceAlertWebhook,
    QuoteImportRequest,
    QuoteImportRow,
    ReconciliationSummaryOut,
    RobinhoodOrderImportRequest,
    RobinhoodOrderOut,
    WebhookIngestResponse,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_quote_map(conn: sqlite3.Connection) -> dict[str, float]:
    return {
        row["symbol"]: float(row["price_usd"])
        for row in conn.execute("SELECT symbol, price_usd FROM quote_cache")
    }


def upsert_quotes(conn: sqlite3.Connection, quotes: list[QuoteImportRow]) -> int:
    upserted = 0
    now = _iso_now()
    for quote in quotes:
        if quote.price_usd <= 0:
            continue
        symbol = quote.symbol.upper().strip()
        conn.execute(
            """
            INSERT INTO quote_cache (symbol, price_usd, source, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                price_usd = excluded.price_usd,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (symbol, quote.price_usd, quote.source, now),
        )
        upserted += 1
    return upserted


def import_quotes(conn: sqlite3.Connection, payload: QuoteImportRequest) -> int:
    return upsert_quotes(conn, payload.quotes)


def get_pending_market_signals(conn: sqlite3.Connection) -> list[MarketSignalOut]:
    return [
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
            WHERE check_needed = 1 AND consumed_at IS NULL
            ORDER BY id ASC
            LIMIT 20
            """
        )
    ]


def ingest_price_alert(conn: sqlite3.Connection, payload: PriceAlertWebhook) -> WebhookIngestResponse:
    cursor = conn.execute(
        """
        INSERT INTO market_signals (
            signal_type, symbol, message, check_needed, source, payload_json
        ) VALUES (?, ?, ?, 1, ?, ?)
        """,
        (
            payload.signal_type,
            payload.symbol.upper().strip() if payload.symbol else None,
            payload.message.strip(),
            payload.source,
            json.dumps(payload.payload) if payload.payload else None,
        ),
    )
    return WebhookIngestResponse(
        signal_id=cursor.lastrowid,
        check_needed=True,
        message="Market signal recorded; automation context will show check_needed.",
    )


def consume_pending_market_signals(conn: sqlite3.Connection) -> int:
    now = _iso_now()
    cursor = conn.execute(
        """
        UPDATE market_signals
        SET check_needed = 0, consumed_at = ?
        WHERE check_needed = 1 AND consumed_at IS NULL
        """,
        (now,),
    )
    return cursor.rowcount


def _link_order_to_decision(conn: sqlite3.Connection, robinhood_order_id: str) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM decisions
        WHERE order_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (robinhood_order_id,),
    ).fetchone()
    return int(row["id"]) if row else None


def import_robinhood_orders(conn: sqlite3.Connection, payload: RobinhoodOrderImportRequest) -> tuple[int, int]:
    upserted = 0
    linked = 0
    now = _iso_now()

    for order in payload.orders:
        decision_id = _link_order_to_decision(conn, order.robinhood_order_id)
        if decision_id is not None:
            linked += 1

        conn.execute(
            """
            INSERT INTO robinhood_orders (
                robinhood_order_id, symbol, side, status, quantity, filled_quantity,
                average_fill_price, notional_usd, submitted_at, updated_at_rh,
                raw_json, decision_id, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(robinhood_order_id) DO UPDATE SET
                symbol = excluded.symbol,
                side = excluded.side,
                status = excluded.status,
                quantity = excluded.quantity,
                filled_quantity = excluded.filled_quantity,
                average_fill_price = excluded.average_fill_price,
                notional_usd = excluded.notional_usd,
                submitted_at = excluded.submitted_at,
                updated_at_rh = excluded.updated_at_rh,
                raw_json = excluded.raw_json,
                decision_id = COALESCE(excluded.decision_id, robinhood_orders.decision_id),
                synced_at = excluded.synced_at
            """,
            (
                order.robinhood_order_id,
                order.symbol.upper(),
                order.side.lower(),
                order.status.lower(),
                order.quantity,
                order.filled_quantity,
                order.average_fill_price,
                order.notional_usd,
                order.submitted_at,
                order.updated_at_rh,
                json.dumps(order.raw_json) if order.raw_json else None,
                decision_id,
                now,
            ),
        )
        upserted += 1

    relink = conn.execute(
        """
        UPDATE robinhood_orders
        SET decision_id = (
            SELECT d.id FROM decisions d
            WHERE d.order_id = robinhood_orders.robinhood_order_id
            ORDER BY d.id DESC
            LIMIT 1
        )
        WHERE decision_id IS NULL
        """
    )
    linked += relink.rowcount

    return upserted, linked


def get_robinhood_orders(conn: sqlite3.Connection, limit: int = 50) -> list[RobinhoodOrderOut]:
    orders = []
    for row in conn.execute(
        """
        SELECT id, robinhood_order_id, symbol, side, status, quantity, filled_quantity,
               average_fill_price, notional_usd, decision_id, synced_at, created_at
        FROM robinhood_orders
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ):
        decision_id = row["decision_id"]
        if decision_id is not None:
            reconciliation_status = "linked"
        else:
            reconciliation_status = "unmatched_order"
        orders.append(
            RobinhoodOrderOut(
                id=row["id"],
                robinhood_order_id=row["robinhood_order_id"],
                symbol=row["symbol"],
                side=row["side"],
                status=row["status"],
                quantity=row["quantity"],
                filled_quantity=row["filled_quantity"],
                average_fill_price=row["average_fill_price"],
                notional_usd=row["notional_usd"],
                decision_id=decision_id,
                reconciliation_status=reconciliation_status,
                synced_at=row["synced_at"],
                created_at=row["created_at"],
            )
        )
    return orders


def get_reconciliation_summary(conn: sqlite3.Connection) -> ReconciliationSummaryOut:
    total_orders = conn.execute("SELECT COUNT(*) AS c FROM robinhood_orders").fetchone()["c"]
    linked_orders = conn.execute(
        "SELECT COUNT(*) AS c FROM robinhood_orders WHERE decision_id IS NOT NULL"
    ).fetchone()["c"]
    decisions_with_order_id = conn.execute(
        """
        SELECT COUNT(*) AS c FROM decisions
        WHERE order_id IS NOT NULL AND trim(order_id) != ''
        """
    ).fetchone()["c"]
    unmatched_decisions = conn.execute(
        """
        SELECT COUNT(*) AS c FROM decisions d
        WHERE d.order_id IS NOT NULL AND trim(d.order_id) != ''
          AND NOT EXISTS (
              SELECT 1 FROM robinhood_orders o
              WHERE o.robinhood_order_id = d.order_id
          )
        """
    ).fetchone()["c"]

    return ReconciliationSummaryOut(
        total_orders=total_orders,
        linked_orders=linked_orders,
        unmatched_orders=total_orders - linked_orders,
        decisions_with_order_id=decisions_with_order_id,
        unmatched_decisions=unmatched_decisions,
    )


def mark_position_with_quotes(
    symbol: str,
    quantity: float,
    avg_cost: float,
    quote_map: dict[str, float],
) -> tuple[float, float | None, float, float | None]:
    cost_basis = quantity * avg_cost
    last_price = quote_map.get(symbol.upper())
    if last_price is not None and last_price > 0:
        market_value = quantity * last_price
        unrealized_pnl = market_value - cost_basis
        return market_value, last_price, cost_basis, unrealized_pnl
    market_value = cost_basis
    return market_value, None, cost_basis, None
