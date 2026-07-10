# Manual Ticker Scout

Run this **manually** (Cursor chat or a one-off automation) when you want fresh ticker ideas for the daily lanes. It does **not** trade. It only proposes symbols; you promote the ones you like into the discovery pool.

## Goal

Find 5–15 liquid equity/ETF candidates the daily research lanes are not already covering, with a short thesis each. Store them in the API for review.

## Tools

- Robinhood Trading MCP
- HTTP access to MTA-Lab API (write key)

## Steps

1. `GET {API_BASE}/api/automation/discovery/candidates`
   - Note `core_watchlist`, `candidate_pool`, `allowed_symbols`, and any `pending_proposals`.
2. Gather market ideas via Robinhood MCP (pick 2–3 sources, not all):
   - `get_popular_watchlists` → follow up with `get_watchlist_items` on lists like Daily Movers / Most Popular
   - `get_scans` / `run_scan` if you have a saved screener
   - `get_earnings_calendar` for the next 7–14 days (high market-cap names)
   - `get_equity_quotes` / `get_equity_fundamentals` to sanity-check liquidity and price
3. Filter hard:
   - Prefer liquid large/mid-cap names and major ETFs
   - Skip symbols already in `allowed_symbols` unless you have a new thesis for discovery_pool placement
   - Skip illiquid / sub-$5 / obscure tickers unless thesis is exceptional
   - Cap at **15** proposals per scout run
4. `POST {API_BASE}/api/admin/symbol-proposals/import` with header `X-API-Key: {WRITE_API_KEY}`:

```json
{
  "scout_run_id": "scout-2026-07-10-manual",
  "proposals": [
    {
      "symbol": "NVDA",
      "source": "robinhood_popular",
      "score": 0.78,
      "tags": ["mega-cap", "semiconductor", "momentum"],
      "thesis": "Appears on Daily Movers; strong relative strength vs QQQ; liquid enough for paper discovery."
    }
  ]
}
```

5. Summarize what you proposed and what you skipped. Do **not** promote or change strategy yourself unless the user asks.

## After the scout (you / operator)

Review:

```bash
curl -sS "$API/api/admin/symbol-proposals?status=pending" \
  -H "X-API-Key: $WRITE_KEY" | python3 -m json.tool
```

Promote selected IDs into `allowed_symbols` + `discovery_pool` (enables discovery, rebinds lanes):

```bash
curl -sS -X POST "$API/api/admin/symbol-proposals/promote" \
  -H "X-API-Key: $WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"proposal_ids": [1, 2, 3], "enable_discovery": true, "discovery_max_per_run": 2, "update_lanes": true}'
```

Dismiss noise:

```bash
curl -sS -X POST "$API/api/admin/symbol-proposals/4/dismiss" \
  -H "X-API-Key: $WRITE_KEY"
```

## How daily lanes use the result

After promote:

- Symbols land in strategy `allowed_symbols` and `discovery_pool`
- `symbol_discovery_enabled` turns on (if requested)
- Lanes 1–3 may optionally research up to `discovery_max_per_run` extras from that pool each day

Pending proposals appear in context as `symbol_discovery.pending_proposals` for awareness only — **daily lanes still cannot trade them until promoted**.

## Related

- [research-prompt.md](./research-prompt.md) — daily lane run order (step 7b discovery)
- [multi-lane-simulation.md](./multi-lane-simulation.md)
