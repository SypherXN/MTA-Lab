import sqlite3
from datetime import datetime, timezone

from app.freshness_service import evaluate_freshness
from app.integration_service import _get_quote_map, get_robinhood_orders
from app.safety import get_active_strategy
from app.schemas import (
    MarketInputBundleOut,
    MarketInputCheckItemOut,
    MarketInputMoverOut,
    MarketInputQuoteOut,
)

INDEX_SYMBOLS = ("SPY", "QQQ", "DIA")
VOLATILITY_SYMBOLS = ("VIX", "VIXY", "UVXY")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quote_rows(
    conn: sqlite3.Connection,
    symbols: tuple[str, ...],
) -> list[MarketInputQuoteOut]:
    if not symbols:
        return []
    placeholders = ",".join("?" for _ in symbols)
    rows = conn.execute(
        f"""
        SELECT symbol, price_usd, source, updated_at
        FROM quote_cache
        WHERE upper(symbol) IN ({placeholders})
        ORDER BY symbol
        """,
        [s.upper() for s in symbols],
    )
    return [
        MarketInputQuoteOut(
            symbol=row["symbol"],
            price_usd=float(row["price_usd"]),
            source=row["source"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def _watchlist_movers(
    conn: sqlite3.Connection,
    watchlist: list[str],
    quote_map: dict[str, float],
) -> list[MarketInputMoverOut]:
    movers: list[MarketInputMoverOut] = []
    for row in conn.execute(
        "SELECT symbol, quantity, avg_cost FROM simulated_positions ORDER BY symbol"
    ):
        symbol = row["symbol"].upper()
        if symbol not in {s.upper() for s in watchlist}:
            continue
        price = quote_map.get(symbol)
        avg_cost = float(row["avg_cost"])
        change_pct = None
        if price is not None and avg_cost > 0:
            change_pct = round(((price - avg_cost) / avg_cost) * 100, 2)
        movers.append(
            MarketInputMoverOut(
                symbol=symbol,
                price_usd=price,
                change_pct=change_pct,
                detail="vs simulated avg cost" if change_pct is not None else "no quote mark",
            )
        )

    for symbol in watchlist:
        upper = symbol.upper()
        if any(m.symbol == upper for m in movers):
            continue
        price = quote_map.get(upper)
        if price is not None:
            movers.append(
                MarketInputMoverOut(
                    symbol=upper,
                    price_usd=price,
                    change_pct=None,
                    detail="watchlist quote; day change from MCP",
                )
            )

    movers.sort(key=lambda item: abs(item.change_pct or 0), reverse=True)
    return movers


def get_market_input_bundle(conn: sqlite3.Connection) -> MarketInputBundleOut:
    from app.services import get_simulated_portfolio

    strategy = get_active_strategy(conn)
    watchlist = strategy.rules.watchlist or strategy.rules.allowed_symbols
    quote_map = _get_quote_map(conn)

    watchlist_quotes = _quote_rows(conn, tuple(w.upper() for w in watchlist))
    watchlist_with_quotes = {q.symbol.upper() for q in watchlist_quotes}
    index_quotes = _quote_rows(conn, INDEX_SYMBOLS)
    volatility_quotes = _quote_rows(conn, VOLATILITY_SYMBOLS)

    portfolio = get_simulated_portfolio(conn)
    orders = get_robinhood_orders(conn, limit=500)
    freshness = evaluate_freshness(conn)

    news_count = conn.execute("SELECT COUNT(*) AS c FROM news_event_summaries").fetchone()["c"]

    all_watchlist_quoted = bool(watchlist) and all(
        symbol.upper() in watchlist_with_quotes for symbol in watchlist
    )
    has_index = any(q.symbol.upper() in {"SPY", "QQQ"} for q in index_quotes)
    has_orders = len(orders) > 0
    has_positions = len(portfolio.positions) > 0 or portfolio.cash_usd > 0

    checklist = [
        MarketInputCheckItemOut(
            key="watchlist_quotes",
            label="Watchlist quotes",
            required=True,
            present=all_watchlist_quoted,
            source="quote_cache / MCP get_equity_quotes",
            detail=f"{len(watchlist_quotes)}/{len(watchlist)} symbols quoted",
        ),
        MarketInputCheckItemOut(
            key="index_state",
            label="Broad index state (SPY/QQQ)",
            required=True,
            present=has_index,
            source="quote_cache / MCP",
            detail=f"{len(index_quotes)} index quotes cached",
        ),
        MarketInputCheckItemOut(
            key="volatility_proxy",
            label="Volatility proxy (VIX/VIXY)",
            required=False,
            present=len(volatility_quotes) > 0,
            source="quote_cache / MCP",
            detail=f"{len(volatility_quotes)} vol proxy quotes cached",
        ),
        MarketInputCheckItemOut(
            key="positions",
            label="Portfolio positions",
            required=True,
            present=has_positions,
            source="simulated portfolio + MCP get_equity_positions",
            detail=f"{len(portfolio.positions)} simulated positions",
        ),
        MarketInputCheckItemOut(
            key="recent_orders",
            label="Recent orders synced",
            required=True,
            present=has_orders,
            source="robinhood_orders table",
            detail=f"{len(orders)} orders in API",
        ),
        MarketInputCheckItemOut(
            key="news_context",
            label="News/event summaries",
            required=False,
            present=news_count > 0,
            source="news_event_summaries / GET /api/automation/news",
            detail=f"{news_count} stored events",
        ),
        MarketInputCheckItemOut(
            key="data_freshness",
            label="Inputs fresh enough for analysis",
            required=True,
            present=freshness.ready_for_analysis,
            source="freshness_checks",
            detail="; ".join(freshness.warnings[:2]) if freshness.warnings else "all required sources fresh",
        ),
    ]

    ready = all(item.present for item in checklist if item.required)

    return MarketInputBundleOut(
        checklist=checklist,
        ready=ready,
        watchlist=watchlist,
        watchlist_quotes=watchlist_quotes,
        index_quotes=index_quotes,
        volatility_quotes=volatility_quotes,
        movers=_watchlist_movers(conn, watchlist, quote_map),
        simulated_portfolio=portfolio,
        recent_orders_count=len(orders),
        gathered_at=_iso_now(),
    )
