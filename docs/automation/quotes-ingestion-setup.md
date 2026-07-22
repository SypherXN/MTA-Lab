# Quote Cache Ingestion Setup

The API `freshness_checks` gate treats **quotes** as stale after **240 minutes** (4 hours). Lane 4 (explorer) and other lanes can gather fresh Robinhood MCP prices but still be blocked if the shared `quote_cache` was last updated by an earlier run.

Fix with **two layers**:

1. **VM cron** — `ingest_quotes.py` refreshes the cache on a schedule.
2. **Research prompt** — each lane imports MCP quotes via `POST /api/admin/quotes/import` **before** checking `market-inputs` / `freshness_checks`.

## VM cron (recommended)

### Script

`api/scripts/ingest_quotes.py` fetches batch prices from Yahoo Finance spark API for:

- Active strategy **watchlist**
- **discovery_pool** symbols
- Index symbols (SPY, QQQ, DIA)
- Volatility proxies (VIX, VIXY, UVXY)

### Manual test

```bash
cd ~/MTA-Lab/api
source .venv/bin/activate
python3 scripts/ingest_quotes.py --dry-run
python3 scripts/ingest_quotes.py
```

### Cron

Append `api/deploy/quotes-ingest.cron.example` to the VM user crontab, or add:

```cron
*/30 * * * 1-5 cd /home/ubuntu/MTA-Lab/api && .venv/bin/python3 scripts/ingest_quotes.py >> data/quotes-ingest.log 2>&1
```

### Verify

```bash
curl -sS "$MTA_API_BASE/api/dashboard/freshness/check" -H "X-API-Key: $READ_OR_WRITE_KEY" | python3 -m json.tool
# quotes: is_stale=false, age_minutes < 240
```

## Agent-side import (required in research prompt)

After Robinhood `get_equity_quotes` in step 5, call:

```http
POST /api/admin/quotes/import
X-API-Key: {WRITE_API_KEY}

{
  "quotes": [
    {"symbol": "SPY", "price_usd": 755.12, "source": "robinhood_mcp"},
    {"symbol": "QQQ", "price_usd": 726.40, "source": "robinhood_mcp"}
  ]
}
```

Then proceed to `GET /api/automation/market-inputs` so `ready_for_analysis` reflects live prices.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `quotes` stale between lane runs | Enable cron; confirm `data/quotes-ingest.log` |
| Lane 4 holds despite strong RS | Check freshness age; run `ingest_quotes.py` manually |
| `ready_for_analysis=false` only quotes | Cron + agent import; quotes max age is 240m |
| Yahoo fetch fails | Retry; check outbound HTTPS from VM |

## Related

- [news-ingestion-setup.md](./news-ingestion-setup.md)
- [research-prompt.md](./research-prompt.md)
- [multi-cadence.md](./multi-cadence.md)
