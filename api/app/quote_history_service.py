"""Persist index/equity prices over time and backfill from Yahoo for market comparison."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx

USER_AGENT = "MTA-Lab-QuoteHistory/1.0"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
DEFAULT_BENCHMARK = "SPY"
BENCHMARK_SYMBOLS = ("SPY", "QQQ", "DIA")


def _should_auto_backfill() -> bool:
    return os.environ.get("MTA_SKIP_BENCHMARK_BACKFILL", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def record_quote_history(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    price_usd: float,
    source: str = "import",
    observed_at: str | None = None,
) -> None:
    if price_usd <= 0:
        return
    conn.execute(
        """
        INSERT INTO quote_history (symbol, observed_at, price_usd, source)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol, observed_at) DO UPDATE SET
            price_usd = excluded.price_usd,
            source = excluded.source
        """,
        (symbol.upper().strip(), observed_at or _iso_now(), float(price_usd), source),
    )


def get_price_as_of(
    conn: sqlite3.Connection,
    symbol: str,
    at: str,
) -> float | None:
    row = conn.execute(
        """
        SELECT price_usd
        FROM quote_history
        WHERE symbol = ?
          AND datetime(observed_at) <= datetime(?)
        ORDER BY datetime(observed_at) DESC
        LIMIT 1
        """,
        (symbol.upper().strip(), at),
    ).fetchone()
    if row is not None:
        return float(row["price_usd"])
    fallback = conn.execute(
        """
        SELECT price_usd
        FROM quote_history
        WHERE symbol = ?
        ORDER BY datetime(observed_at) ASC
        LIMIT 1
        """,
        (symbol.upper().strip(),),
    ).fetchone()
    if fallback is None:
        cache = conn.execute(
            "SELECT price_usd FROM quote_cache WHERE symbol = ?",
            (symbol.upper().strip(),),
        ).fetchone()
        return float(cache["price_usd"]) if cache else None
    return float(fallback["price_usd"])


def get_quote_history(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    since: str | None = None,
    until: str | None = None,
    limit: int = 2000,
) -> list[sqlite3.Row]:
    query = """
        SELECT symbol, observed_at, price_usd, source
        FROM quote_history
        WHERE symbol = ?
    """
    params: list = [symbol.upper().strip()]
    if since:
        query += " AND datetime(observed_at) >= datetime(?)"
        params.append(since)
    if until:
        query += " AND datetime(observed_at) <= datetime(?)"
        params.append(until)
    query += " ORDER BY datetime(observed_at) ASC LIMIT ?"
    params.append(limit)
    return list(conn.execute(query, params))


def _history_coverage(
    conn: sqlite3.Connection, symbol: str
) -> tuple[str | None, str | None, int]:
    row = conn.execute(
        """
        SELECT MIN(observed_at) AS first_at, MAX(observed_at) AS last_at, COUNT(*) AS n
        FROM quote_history
        WHERE symbol = ?
        """,
        (symbol.upper().strip(),),
    ).fetchone()
    return (
        row["first_at"] if row else None,
        row["last_at"] if row else None,
        int(row["n"] or 0) if row else 0,
    )


def fetch_yahoo_daily_closes(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    client: httpx.Client | None = None,
) -> list[tuple[str, float]]:
    period1 = int(start.timestamp())
    period2 = int((end + timedelta(days=1)).timestamp())
    url = YAHOO_CHART_URL.format(symbol=symbol.upper().strip())
    own_client = client is None
    if own_client:
        client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=25.0)
    try:
        response = client.get(
            url,
            params={
                "interval": "1d",
                "period1": str(period1),
                "period2": str(period2),
                "events": "div,splits",
            },
        )
        response.raise_for_status()
        payload = response.json()
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not result:
            return []
        timestamps = result.get("timestamp") or []
        closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []
        rows: list[tuple[str, float]] = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            price = float(close)
            if price <= 0:
                continue
            observed = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
            rows.append((observed, price))
        return rows
    finally:
        if own_client and client is not None:
            client.close()


def _snapshot_range(conn: sqlite3.Connection) -> tuple[datetime, datetime]:
    row = conn.execute(
        "SELECT MIN(snapshot_at) AS first_at, MAX(snapshot_at) AS last_at FROM portfolio_snapshots"
    ).fetchone()
    now = datetime.now(timezone.utc)
    first = _parse_ts(row["first_at"] if row else None) or (now - timedelta(days=400))
    last = _parse_ts(row["last_at"] if row else None) or now
    start = min(first, last) - timedelta(days=7)
    end = max(last, now) + timedelta(days=1)
    return start, end


def ensure_benchmark_history(
    conn: sqlite3.Connection,
    *,
    symbols: tuple[str, ...] = BENCHMARK_SYMBOLS,
    force: bool = False,
) -> dict[str, int]:
    """Backfill daily closes from Yahoo when history does not cover snapshot dates."""
    if not _should_auto_backfill() and not force:
        return {symbol: 0 for symbol in symbols}
    start, end = _snapshot_range(conn)
    inserted: dict[str, int] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=25.0) as client:
        for symbol in symbols:
            first_at, last_at, count = _history_coverage(conn, symbol)
            first_dt = _parse_ts(first_at)
            last_dt = _parse_ts(last_at)
            needs_fetch = force or count == 0
            if not needs_fetch and first_dt is not None and first_dt > start + timedelta(days=5):
                needs_fetch = True
            if not needs_fetch and last_dt is not None and last_dt < end - timedelta(days=5):
                needs_fetch = True
            if not needs_fetch:
                inserted[symbol] = 0
                continue
            try:
                bars = fetch_yahoo_daily_closes(symbol, start, end, client=client)
            except Exception:
                inserted[symbol] = 0
                continue
            written = 0
            for observed_at, price in bars:
                record_quote_history(
                    conn,
                    symbol=symbol,
                    price_usd=price,
                    source="yahoo-chart",
                    observed_at=observed_at,
                )
                written += 1
            inserted[symbol] = written
    return inserted
