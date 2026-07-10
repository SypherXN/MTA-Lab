# Manual / Scheduled Ticker Scout

Find liquid ticker ideas for the daily lanes. Scout runs **do not trade**. They propose symbols; promotion (manual or auto) adds them to `allowed_symbols` + `discovery_pool`.

## Modes

| Mode | When | Promote |
|------|------|---------|
| **Manual** | Ad-hoc Cursor chat | You review, then `POST .../promote` |
| **Scheduled automation** | Weekly Cursor Automation | Import then `POST .../auto-promote` |

## Goal

Find 5–15 liquid equity/ETF candidates outside the current watchlist, with a short thesis each.

## Tools

- Robinhood Trading MCP
- HTTP access to MTA-Lab API (write key)

## Steps

1. `GET {API_BASE}/api/automation/discovery/candidates`
   - Note `core_watchlist`, `candidate_pool`, `allowed_symbols`, and `pending_proposals`.
2. Gather ideas via Robinhood MCP (pick 2–3 sources):
   - `get_popular_watchlists` → `get_watchlist_items` (Daily Movers / Most Popular)
   - `get_scans` / `run_scan` if a saved screener exists
   - `get_earnings_calendar` for the next 7–14 days (high market-cap)
   - `get_equity_quotes` / `get_equity_fundamentals` for liquidity sanity checks
3. Filter hard:
   - Prefer liquid large/mid-cap names and major ETFs
   - Skip illiquid / sub-$5 / obscure tickers unless thesis is exceptional
   - Cap at **15** proposals per scout run
4. `POST {API_BASE}/api/admin/symbol-proposals/import` with `X-API-Key: {WRITE_API_KEY}`:

```json
{
  "scout_run_id": "scout-2026-07-10-weekly",
  "proposals": [
    {
      "symbol": "NVDA",
      "source": "robinhood_popular",
      "score": 0.78,
      "tags": ["mega-cap", "semiconductor", "momentum"],
      "thesis": "Appears on Daily Movers; strong relative strength vs QQQ; liquid for paper discovery."
    }
  ]
}
```

5. **Scheduled mode only** — auto-add high-confidence names:

```bash
POST {API_BASE}/api/admin/symbol-proposals/auto-promote
{
  "min_score": 0.65,
  "max_symbols": 8,
  "enable_discovery": true,
  "discovery_max_per_run": 2,
  "update_lanes": true
}
```

6. Summarize proposed / auto-promoted / skipped. Do not place trades.

## Manual review (optional)

```bash
curl -sS "$API/api/admin/symbol-proposals?status=pending" \
  -H "X-API-Key: $WRITE_KEY" | python3 -m json.tool

curl -sS -X POST "$API/api/admin/symbol-proposals/promote" \
  -H "X-API-Key: $WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"proposal_ids":[1,2,3],"enable_discovery":true,"update_lanes":true}'

curl -sS -X POST "$API/api/admin/symbol-proposals/4/dismiss" \
  -H "X-API-Key: $WRITE_KEY"
```

## Cursor Automation setup (weekly)

1. Create automation `mta-ticker-scout`
2. Schedule: `0 14 * * 0` (Sunday 14:00 UTC ≈ Sunday morning PT) — adjust timezone in UI
3. Model: Composer 2.5
4. Tools: Robinhood MCP + API HTTP
5. Paste this file as the prompt; replace `{API_BASE}` and `{WRITE_API_KEY}`
6. End every run with **import + auto-promote**

Env defaults on the API (optional):

```bash
MTA_SCOUT_AUTO_PROMOTE_MIN_SCORE=0.65
MTA_SCOUT_AUTO_PROMOTE_MAX_SYMBOLS=8
```

## How daily lanes use results

After promote / auto-promote:

- Symbols land in strategy `allowed_symbols` and `discovery_pool`
- `symbol_discovery_enabled` turns on
- Lanes 1–3 may research up to `discovery_max_per_run` extras from that pool each day

Pending (not yet promoted) proposals appear in `symbol_discovery.pending_proposals` for awareness only — **cannot be traded until promoted**.

## Related

- [research-prompt.md](./research-prompt.md) — daily lane run order (step 7b discovery)
- [multi-lane-simulation.md](./multi-lane-simulation.md) — live promotion + shadow sync
