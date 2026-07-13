# News Ingestion Setup

News is **global** — all lanes read the same `news_event_summaries` table. You need **one** ingest path, not per-lane news jobs.

## Recommended: VM cron (reliable)

Runs before weekday research automations.

### 1. Script

`api/scripts/ingest_news_rss.py` fetches Google News RSS for:

- Active strategy **watchlist**
- **discovery_pool** symbols
- Two macro queries (broad market + Fed)

Dedupes via `source=google-news-rss` + article URL (`external_id`).

### 2. Manual test

```bash
cd ~/MTA-Lab/api
source .venv/bin/activate
python3 scripts/ingest_news_rss.py --dry-run
python3 scripts/ingest_news_rss.py
```

### 3. Cron (UTC)

Add on the OCI VM (6:00 AM Pacific = 13:00 UTC during PDT):

```cron
0 13 * * 1-5 cd /home/ubuntu/MTA-Lab/api && .venv/bin/python3 scripts/ingest_news_rss.py >> data/news-ingest.log 2>&1
```

Or append `api/deploy/news-ingest.cron.example` to your user crontab.

### 4. Verify

```bash
curl -sS "$MTA_API_BASE/api/dashboard/freshness/check" -H "Authorization: Bearer $DASHBOARD_TOKEN" | python3 -m json.tool
# news source: is_stale=false, age_minutes < 1440

curl -sS "$MTA_API_BASE/api/automation/news?limit=5" -H "X-API-Key: $READ_OR_WRITE_KEY" | python3 -m json.tool
```

## Optional: Cursor automation (`mta-news`)

Use for earnings calendar + curated headlines when RSS is too thin. See [news-prompt.md](./news-prompt.md).

Schedule **before** lane research (`mta-acct1-lane1-sim`, etc.).

## Research lanes after ingest

Lanes should **read** shared news, not each re-ingest everything:

- `GET /api/automation/context` → `recent_news`
- `GET /api/automation/news?symbol=SYMBOL`
- Only call `POST /api/admin/news/import` when they find **new** material not already in the API

Lane 3 (news-event) still needs catalysts in the store — the cron + `mta-news` job feeds it.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `news` always stale | Run `ingest_news_rss.py`; check `data/news-ingest.log` |
| `inserted=0 skipped=N` | Normal — dedup; headlines already stored |
| Lane 3 skips all symbols | News empty or no catalysts; run ingest before lane 3 |
| Research lanes duplicate ingest | Tighten prompt: skip import when news age &lt; 6h |

## Related

- [multi-lane-simulation.md](./multi-lane-simulation.md) — shared quote cache + news
- [research-prompt.md](./research-prompt.md)
