#!/usr/bin/env python3
"""Ingest headline summaries from Google News RSS for the active watchlist.

Runs on the VM via cron before daily research lanes. Dedupes by source + external_id.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import httpx

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.config import settings  # noqa: E402
from app.database import get_connection, init_db  # noqa: E402
from app.freshness_service import evaluate_freshness  # noqa: E402
from app.news_service import ingest_news_events  # noqa: E402
from app.safety import get_active_strategy  # noqa: E402
from app.schemas import NewsEventIn  # noqa: E402

USER_AGENT = "MTA-Lab-NewsIngest/1.0"
MACRO_QUERIES = (
    ("macro", "US stock market outlook"),
    ("macro", "Federal Reserve economy"),
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_pub_date(value: str | None) -> str:
    if not value:
        return _iso_now()
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return _iso_now()


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip()


def _rss_url(query: str) -> str:
    encoded = quote_plus(query)
    return (
        "https://news.google.com/rss/search?"
        f"q={encoded}+when:1d&hl=en-US&gl=US&ceid=US:en"
    )


def _fetch_items(client: httpx.Client, query: str, *, max_items: int) -> list[dict[str, str]]:
    response = client.get(_rss_url(query), timeout=20.0)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    channel = root.find("channel")
    if channel is None:
        return []

    items: list[dict[str, str]] = []
    for item in channel.findall("item")[:max_items]:
        title = _clean_text(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        description = _clean_text(item.findtext("description"))
        pub_date = item.findtext("pubDate")
        if not title or not link:
            continue
        summary = title if not description else f"{title} — {description[:240]}"
        items.append(
            {
                "summary": summary[:500],
                "link": link,
                "event_at": _parse_pub_date(pub_date),
            }
        )
    return items


def _collect_symbols(watchlist: list[str], discovery_pool: list[str]) -> list[str | None]:
    symbols: list[str | None] = []
    seen: set[str] = set()
    for raw in (*watchlist, *discovery_pool):
        symbol = raw.upper().strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    for _, query in MACRO_QUERIES:
        key = f"macro:{query}"
        if key in seen:
            continue
        seen.add(key)
        symbols.append(None)
    return symbols


def _query_for_symbol(symbol: str | None, macro_index: int) -> tuple[str, str]:
    if symbol:
        return symbol, f"{symbol} stock"
    _, query = MACRO_QUERIES[macro_index]
    return "macro", query


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Google News RSS headlines into MTA-Lab.")
    parser.add_argument("--max-per-symbol", type=int, default=3, help="Max headlines per symbol/query")
    parser.add_argument(
        "--skip-if-fresh-minutes",
        type=int,
        default=360,
        help="Exit 0 without fetching when news was updated within this many minutes (0 = always run)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print counts only; do not write")
    args = parser.parse_args()

    init_db()
    conn = get_connection()
    try:
        if args.skip_if_fresh_minutes > 0:
            freshness = evaluate_freshness(conn)
            news = next((s for s in freshness.sources if s.source_key == "news"), None)
            if (
                news is not None
                and news.last_updated_at
                and news.age_minutes is not None
                and news.age_minutes < args.skip_if_fresh_minutes
                and not news.is_stale
            ):
                print(
                    f"News fresh ({news.age_minutes:.0f}m old < {args.skip_if_fresh_minutes}m); skipping ingest."
                )
                return 0

        strategy = get_active_strategy(conn)
        symbols = _collect_symbols(strategy.rules.watchlist, strategy.rules.discovery_pool)
        if not symbols:
            print("No watchlist symbols configured; nothing to ingest.", file=sys.stderr)
            return 1

        events: list[NewsEventIn] = []
        macro_index = 0
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            for symbol in symbols:
                if symbol is None:
                    label, query = _query_for_symbol(None, macro_index)
                    macro_index += 1
                else:
                    label, query = _query_for_symbol(symbol, 0)
                try:
                    items = _fetch_items(client, query, max_items=args.max_per_symbol)
                except httpx.HTTPError as exc:
                    print(f"WARN: fetch failed for {label}: {exc}", file=sys.stderr)
                    continue
                for item in items:
                    events.append(
                        NewsEventIn(
                            symbol=None if label == "macro" else label,
                            source="google-news-rss",
                            event_at=item["event_at"],
                            event_type="headline" if label != "macro" else "macro",
                            importance=0.6,
                            summary=item["summary"],
                            external_id=item["link"],
                        )
                    )

        if args.dry_run:
            print(f"dry-run: would ingest {len(events)} event(s) for {len(symbols)} symbol/query target(s)")
            return 0

        if not events:
            print("No RSS items fetched.", file=sys.stderr)
            return 1

        inserted, skipped = ingest_news_events(conn, events)
        conn.commit()
        print(f"ingested inserted={inserted} skipped={skipped} fetched={len(events)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
