# MTA-Lab News Ingest Automation (`mta-news`)

Shared news pool for **all lanes**. Research lanes read `GET /api/automation/news`; they do not each maintain separate news stores.

Use this when the VM RSS cron ([news-ingestion-setup.md](./news-ingestion-setup.md)) is not enough — e.g. earnings detail from Robinhood MCP or deeper headline curation.

## Why a dedicated automation?

Research lanes often **skip** `POST /api/admin/news/import` because:

- Robinhood MCP has quotes/earnings, not headline feeds
- Plan step 8 says ingest "when found" — agents treat it as optional
- `GET /api/automation/news` returns empty on a fresh DB, so agents assume there is no news step

## Trigger

- **Name:** `mta-news`
- **Schedule:** `0 13 * * 1-5` (6:00 AM Pacific / 30+ min before weekday research lanes)
- **Model:** Composer 2.5 Fast (or similar — no trading decisions)
- **Repository:** none
- **Tools:** Robinhood Trading MCP + HTTP to MTA-Lab API + **web search** (required for headlines)

## Required run order

1. `GET {API_BASE}/api/dashboard/freshness/check` (or automation context freshness)
   - If `news` source is **not** stale and `age_minutes < 360`, exit with summary: "News already fresh."
2. `GET {API_BASE}/api/automation/context?lane_id=1`
   - Read `strategy.rules.watchlist`, `discovery_pool`, and `allowed_symbols`.
3. **Earnings calendar (Robinhood MCP)**
   - `get_earnings_calendar` for the next 7 days
   - For watchlist symbols reporting soon, `get_earnings_results` when available
4. **Headlines (web search)**
   - For each watchlist symbol + 1–2 macro queries (Fed, broad market), find material headlines from the last 24h
5. `POST {API_BASE}/api/admin/news/import` with `X-API-Key: {WRITE_API_KEY}`
   - **At least one event per watchlist symbol** (or explain in summary why none found)
   - Use stable `external_id` (URL or `source:headline-id`) for dedup
   - Do **not** log a research run — this job only ingests news

### Example import body

```json
{
  "events": [
    {
      "symbol": "AAPL",
      "source": "reuters",
      "event_at": "2026-07-13T14:00:00+00:00",
      "event_type": "headline",
      "importance": 0.7,
      "sentiment": 0.1,
      "summary": "Apple supplier guidance points to steady iPhone demand into fall.",
      "external_id": "https://example.com/article-123"
    },
    {
      "source": "earnings-cal",
      "event_at": "2026-07-14T12:00:00+00:00",
      "event_type": "earnings",
      "importance": 0.8,
      "summary": "JPM reports before open Jul 14; bank earnings week underway.",
      "external_id": "earnings:JPM:2026-07-14"
    }
  ]
}
```

6. `GET {API_BASE}/api/dashboard/freshness/check` — confirm `news` is no longer stale.
7. Summarize: symbols covered, `inserted` / `skipped` counts, any symbols with no material news.

## Rules

- **No trades**, no `POST /api/automation/runs`, no lane-specific portfolio changes
- News is **global** — one ingest benefits lanes 1–4
- Skip duplicate work when RSS cron already refreshed news in the last 6 hours
- Prefer factual summaries; include date/source in `summary` text

## Related

- [news-ingestion-setup.md](./news-ingestion-setup.md) — VM cron (recommended baseline)
- [research-prompt.md](./research-prompt.md) — lanes consume shared news, do not re-fetch if fresh
- [multi-cadence.md](./multi-cadence.md) — schedule table
