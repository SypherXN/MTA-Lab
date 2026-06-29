from datetime import datetime, timezone

import sqlite3

from app.freshness_service import touch_data_source
from app.schemas import NewsEventIn, NewsEventOut


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_out(row: sqlite3.Row) -> NewsEventOut:
    return NewsEventOut(
        id=row["id"],
        symbol=row["symbol"],
        source=row["source"],
        event_at=row["event_at"],
        event_type=row["event_type"],
        importance=row["importance"],
        sentiment=row["sentiment"],
        summary=row["summary"],
        ingested_at=row["ingested_at"],
    )


def ingest_news_events(
    conn: sqlite3.Connection,
    events: list[NewsEventIn],
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    latest_at: str | None = None

    for event in events:
        symbol = event.symbol.upper() if event.symbol else None
        if event.external_id:
            existing = conn.execute(
                """
                SELECT id FROM news_event_summaries
                WHERE source = ? AND external_id = ?
                """,
                (event.source, event.external_id),
            ).fetchone()
            if existing is not None:
                skipped += 1
                continue

        ingested_at = _iso_now()
        conn.execute(
            """
            INSERT INTO news_event_summaries (
                symbol, source, event_at, event_type, importance,
                sentiment, summary, external_id, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                event.source,
                event.event_at,
                event.event_type,
                event.importance,
                event.sentiment,
                event.summary.strip(),
                event.external_id,
                ingested_at,
            ),
        )
        inserted += 1
        if latest_at is None or event.event_at > latest_at:
            latest_at = event.event_at

    if inserted > 0:
        touch_data_source(
            conn,
            "news",
            detail=f"{inserted} event(s) ingested",
            updated_at=latest_at or _iso_now(),
        )

    return inserted, skipped


def list_news_events(
    conn: sqlite3.Connection,
    *,
    symbol: str | None = None,
    since: str | None = None,
    limit: int = 50,
) -> list[NewsEventOut]:
    clauses: list[str] = []
    params: list[object] = []

    if symbol:
        clauses.append("(symbol IS NULL OR upper(symbol) = upper(?))")
        params.append(symbol)
    if since:
        clauses.append("event_at >= ?")
        params.append(since)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT id, symbol, source, event_at, event_type, importance,
               sentiment, summary, ingested_at
        FROM news_event_summaries
        {where}
        ORDER BY event_at DESC, id DESC
        LIMIT ?
        """,
        params,
    )
    return [_row_to_out(row) for row in rows]


def get_recent_news_for_watchlist(
    conn: sqlite3.Connection,
    symbols: list[str],
    *,
    limit: int = 20,
) -> list[NewsEventOut]:
    if not symbols:
        return list_news_events(conn, limit=limit)

    upper = [s.upper() for s in symbols]
    placeholders = ",".join("?" for _ in upper)
    rows = conn.execute(
        f"""
        SELECT id, symbol, source, event_at, event_type, importance,
               sentiment, summary, ingested_at
        FROM news_event_summaries
        WHERE symbol IS NULL OR upper(symbol) IN ({placeholders})
        ORDER BY event_at DESC, id DESC
        LIMIT ?
        """,
        [*upper, limit],
    )
    return [_row_to_out(row) for row in rows]
