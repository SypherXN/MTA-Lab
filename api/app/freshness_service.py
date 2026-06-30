from datetime import datetime, timezone

import sqlite3

from app.schemas import DataFreshnessChecksOut, DataSourceFreshnessOut

KNOWN_SOURCES = (
    "quotes",
    "robinhood_orders",
    "portfolio",
    "automation_runs",
    "cursor_usage",
    "market_signals",
    "symbol_memory",
    "news",
)

# Max age before a source is considered stale for agent decisions.
STALE_AFTER_MINUTES: dict[str, int] = {
    "quotes": 240,
    "robinhood_orders": 1440,
    "portfolio": 1440,
    "automation_runs": 2880,
    "cursor_usage": 10080,
    "market_signals": 1440,
    "symbol_memory": 2880,
    "news": 1440,
}

REQUIRED_FOR_ANALYSIS = ("quotes", "portfolio", "automation_runs")

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def touch_data_source(
    conn: sqlite3.Connection,
    source_key: str,
    *,
    detail: str | None = None,
    updated_at: str | None = None,
) -> None:
    now = updated_at or _iso_now()
    conn.execute(
        """
        INSERT INTO data_source_freshness (source_key, last_updated_at, detail, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source_key) DO UPDATE SET
            last_updated_at = excluded.last_updated_at,
            detail = excluded.detail,
            updated_at = excluded.updated_at
        """,
        (source_key, now, detail, now),
    )


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_minutes(last_updated_at: str | None) -> float | None:
    if not last_updated_at:
        return None
    delta = datetime.now(timezone.utc) - _parse_timestamp(last_updated_at)
    return delta.total_seconds() / 60.0


def get_data_freshness(conn: sqlite3.Connection) -> list[DataSourceFreshnessOut]:
    return evaluate_freshness(conn).sources


def evaluate_freshness(conn: sqlite3.Connection) -> DataFreshnessChecksOut:
    rows = {
        row["source_key"]: row
        for row in conn.execute(
            """
            SELECT source_key, last_updated_at, detail, updated_at
            FROM data_source_freshness
            """
        )
    }
    results: list[DataSourceFreshnessOut] = []
    stale_sources: list[str] = []
    missing_sources: list[str] = []
    warnings: list[str] = []

    for key in KNOWN_SOURCES:
        row = rows.get(key)
        max_age = STALE_AFTER_MINUTES.get(key, 1440)
        if row is None or not row["last_updated_at"]:
            missing_sources.append(key)
            results.append(
                DataSourceFreshnessOut(
                    source_key=key,
                    last_updated_at=None,
                    detail=None,
                    updated_at=None,
                    max_age_minutes=max_age,
                    age_minutes=None,
                    is_stale=True,
                )
            )
            continue

        age = _age_minutes(row["last_updated_at"])
        is_stale = age is None or age > max_age
        if is_stale:
            stale_sources.append(key)
            warnings.append(
                f"{key} stale or missing (age={age:.0f}m, max={max_age}m)"
                if age is not None
                else f"{key} has no last_updated_at"
            )
        results.append(
            DataSourceFreshnessOut(
                source_key=row["source_key"],
                last_updated_at=row["last_updated_at"],
                detail=row["detail"],
                updated_at=row["updated_at"],
                max_age_minutes=max_age,
                age_minutes=round(age, 1) if age is not None else None,
                is_stale=is_stale,
            )
        )

    required_stale = [key for key in REQUIRED_FOR_ANALYSIS if key in stale_sources or key in missing_sources]
    ready = len(required_stale) == 0

    if not ready:
        warnings.insert(
            0,
            "Required inputs stale or missing: " + ", ".join(required_stale),
        )

    return DataFreshnessChecksOut(
        sources=results,
        stale_sources=stale_sources,
        missing_sources=missing_sources,
        ready_for_analysis=ready,
        warnings=warnings,
    )

def backfill_freshness_from_existing(conn: sqlite3.Connection) -> None:
    """Seed freshness rows from latest data when table is empty."""
    count = conn.execute("SELECT COUNT(*) AS c FROM data_source_freshness").fetchone()["c"]
    if count > 0:
        return

    quote = conn.execute("SELECT MAX(updated_at) AS t FROM quote_cache").fetchone()["t"]
    if quote:
        touch_data_source(conn, "quotes", updated_at=quote)

    order = conn.execute("SELECT MAX(synced_at) AS t FROM robinhood_orders").fetchone()["t"]
    if order:
        touch_data_source(conn, "robinhood_orders", updated_at=order)

    cash = conn.execute(
        "SELECT updated_at AS t FROM simulated_cash ORDER BY lane_id LIMIT 1"
    ).fetchone()
    if cash and cash["t"]:
        touch_data_source(conn, "portfolio", updated_at=cash["t"])

    run = conn.execute("SELECT MAX(created_at) AS t FROM automation_runs").fetchone()["t"]
    if run:
        touch_data_source(conn, "automation_runs", updated_at=run)

    usage = conn.execute("SELECT MAX(created_at) AS t FROM cursor_usage").fetchone()["t"]
    if usage:
        touch_data_source(conn, "cursor_usage", updated_at=usage)

    signal = conn.execute("SELECT MAX(created_at) AS t FROM market_signals").fetchone()["t"]
    if signal:
        touch_data_source(conn, "market_signals", updated_at=signal)

    memory = conn.execute("SELECT MAX(updated_at) AS t FROM symbol_memory_summaries").fetchone()["t"]
    if memory:
        touch_data_source(conn, "symbol_memory", updated_at=memory)

    news = conn.execute("SELECT MAX(ingested_at) AS t FROM news_event_summaries").fetchone()["t"]
    if news:
        touch_data_source(conn, "news", updated_at=news)
