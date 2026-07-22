#!/usr/bin/env python3
"""Refresh the shared quote cache from Yahoo Finance spark API.

Runs on the VM via cron (and optionally before research lanes) so
freshness_checks.ready_for_analysis stays true between agent runs.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.database import get_connection, init_db  # noqa: E402
from app.freshness_service import evaluate_freshness  # noqa: E402
from app.integration_service import upsert_quotes  # noqa: E402
from app.market_input_service import INDEX_SYMBOLS, VOLATILITY_SYMBOLS  # noqa: E402
from app.safety import get_active_strategy  # noqa: E402
from app.schemas import QuoteImportRow  # noqa: E402

USER_AGENT = "MTA-Lab-QuoteIngest/1.0"
YAHOO_SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
BATCH_SIZE = 10


def _collect_symbols(watchlist: list[str], discovery_pool: list[str]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for raw in (
        *watchlist,
        *discovery_pool,
        *INDEX_SYMBOLS,
        *VOLATILITY_SYMBOLS,
    ):
        symbol = raw.upper().strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def _fetch_batch(client: httpx.Client, batch: list[str]) -> list[QuoteImportRow]:
    if not batch:
        return []
    response = client.get(
        YAHOO_SPARK_URL,
        params={
            "symbols": ",".join(batch),
            "range": "1d",
            "interval": "5m",
        },
        timeout=25.0,
    )
    if response.status_code == 400 and len(batch) > 1:
        quotes: list[QuoteImportRow] = []
        for symbol in batch:
            quotes.extend(_fetch_batch(client, [symbol]))
        return quotes
    response.raise_for_status()
    quotes: list[QuoteImportRow] = []
    payload = response.json()
    for item in payload.get("spark", {}).get("result", []):
        symbol = (item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        responses = item.get("response") or []
        if not responses:
            continue
        meta = responses[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            continue
        price_f = float(price)
        if price_f <= 0:
            continue
        quotes.append(
            QuoteImportRow(
                symbol=symbol,
                price_usd=price_f,
                source="yahoo-spark",
            )
        )
    return quotes


def _fetch_spark_quotes(client: httpx.Client, symbols: list[str]) -> list[QuoteImportRow]:
    quotes: list[QuoteImportRow] = []
    for offset in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[offset : offset + BATCH_SIZE]
        quotes.extend(_fetch_batch(client, batch))
    return quotes


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Yahoo Finance quotes into MTA-Lab.")
    parser.add_argument(
        "--skip-if-fresh-minutes",
        type=int,
        default=30,
        help="Exit 0 without fetching when quotes were updated within this many minutes (0 = always run)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print counts only; do not write")
    args = parser.parse_args()

    init_db()
    conn = get_connection()
    try:
        if args.skip_if_fresh_minutes > 0:
            freshness = evaluate_freshness(conn)
            quotes_row = next((s for s in freshness.sources if s.source_key == "quotes"), None)
            if (
                quotes_row is not None
                and quotes_row.last_updated_at
                and quotes_row.age_minutes is not None
                and quotes_row.age_minutes < args.skip_if_fresh_minutes
                and not quotes_row.is_stale
            ):
                print(
                    f"Quotes fresh ({quotes_row.age_minutes:.0f}m old < {args.skip_if_fresh_minutes}m); skipping ingest."
                )
                return 0

        strategy = get_active_strategy(conn)
        symbols = _collect_symbols(strategy.rules.watchlist, strategy.rules.discovery_pool)
        if not symbols:
            print("No watchlist symbols configured; nothing to ingest.", file=sys.stderr)
            return 1

        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            quotes = _fetch_spark_quotes(client, symbols)

        if args.dry_run:
            print(f"dry-run: would upsert {len(quotes)} quote(s) for {len(symbols)} symbol target(s)")
            return 0

        if not quotes:
            print("No quotes fetched.", file=sys.stderr)
            return 1

        upserted = upsert_quotes(conn, quotes)
        conn.commit()
        print(f"ingested upserted={upserted} fetched={len(quotes)} symbols={len(symbols)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
