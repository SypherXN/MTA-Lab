# MTA-Lab Ticker Explorer Automation Prompt

Use this as the standing instructions for the Cursor Automation named **`mta-explorer`**.

This lane is **paper-only** (`research` role). It widens ticker coverage via `symbol_discovery` while your main lanes stay on a smaller core watchlist.

**Replace before enabling:**

| Placeholder | Example |
|-------------|---------|
| `{API_BASE}` | `https://mta-api.matthewgtran.com` |
| `{WRITE_API_KEY}` | Your `MTA_WRITE_API_KEY` |
| `{EXPLORER_LANE_ID}` | Lane id from setup (e.g. `4`) |

Agent plan: **`v4`** (Ticker Exploration) — loaded via `GET /api/automation/plan?lane_id={EXPLORER_LANE_ID}`.

## Trigger

- Schedule: `30 10 * * 1-5` (weekdays 10:30 AM — offset from main research; adjust timezone in Automations UI)
- Model: Composer 2.5
- Repository: none
- Tools: Robinhood Trading MCP + HTTP access to the MTA-Lab API

Pair with weekly **`mta-ticker-scout`** ([ticker-scout-prompt.md](./ticker-scout-prompt.md)) to feed the discovery pool.

## Required run order

**Lane binding:** Append `?lane_id={EXPLORER_LANE_ID}` on plan, context, memory, and discovery endpoints. Include `"lane_id": {EXPLORER_LANE_ID}` on `POST /api/automation/runs`.

1. `GET {API_BASE}/api/automation/plan?lane_id={EXPLORER_LANE_ID}`
2. `GET {API_BASE}/api/automation/context?lane_id={EXPLORER_LANE_ID}`
   - If `lane_turn.granted` is **false**, exit with a short summary (sequential mode).
   - Confirm `symbol_discovery.enabled` is true. If false, analyze core watchlist only and note that scout/setup is needed.
3. `GET {API_BASE}/api/automation/intervention/check`
4. Robinhood MCP: `get_portfolio`, `get_equity_positions`, `get_equity_quotes` for **core watchlist + SPY + QQQ + VIXY**, `get_equity_orders`
4b. **Quote cache refresh** (required — before step 6)
   - `POST {API_BASE}/api/admin/quotes/import` with **all** prices from step 4 (`X-API-Key: {WRITE_API_KEY}`).
   - Include anchors, discovery picks, indices, and vol proxies you quoted.
   - VM cron (`ingest_quotes.py`) may have run recently — still import MCP quotes every run.
5. `POST {API_BASE}/api/admin/robinhood-orders/import`
6. `GET {API_BASE}/api/automation/market-inputs?lane_id={EXPLORER_LANE_ID}`
7. **Discovery (required)** — `GET {API_BASE}/api/automation/discovery/candidates?lane_id={EXPLORER_LANE_ID}`
   - Analyze `core_watchlist` first (anchors).
   - Research **up to** `max_per_run` symbols from `candidate_pool` (not the entire pool).
   - Use Robinhood MCP to rank pool names:
     - `get_popular_watchlists` → `get_watchlist_items` (Daily Movers / Most Popular)
     - `get_earnings_calendar` (next 7–14 days, large caps)
     - `get_equity_quotes` / `get_equity_fundamentals` for liquidity checks
   - Only trade symbols in `allowed_symbols`.
8. For **each** symbol analyzed (anchors + discovery picks):
   - `GET {API_BASE}/api/automation/symbols/{SYMBOL}/memory?lane_id={EXPLORER_LANE_ID}`
   - Optional: `GET {API_BASE}/api/automation/news?symbol={SYMBOL}` when news may matter
9. Analyze per plan **v4** scoring rules. Produce a decision for every symbol analyzed.
10. Self-critique: discovery count, allowed_symbols, cooldowns, budget.
11. `POST {API_BASE}/api/automation/runs` with `X-API-Key: {WRITE_API_KEY}`

## POST body shape

```json
{
  "automation_name": "mta-explorer",
  "run_type": "daily_research",
  "lane_id": 4,
  "cursor_run_id": "bc-… (required — Cloud Agent ID from this run)",
  "usage": {
    "model": "composer-2.5",
    "cursor_run_id": "bc-… (same as above)",
    "cost_usd": null,
    "input_tokens": null,
    "output_tokens": null
  },
  "market_summary": "Indices firm; researched 2 anchors + 6 discovery names from pool.",
  "self_critique": "Discovery within max_per_run; all trades on allowed_symbols; paper only.",
  "decisions": [
    {
      "symbol": "NVDA",
      "action": "simulated_buy",
      "reason": "Strong RS vs QQQ; liquid mover.",
      "scores": {
        "technical": 0.72,
        "news": 0.55,
        "risk": 0.40,
        "confidence": 0.68
      },
      "action_rationale": "Top-ranked discovery pick; trend aligns with index.",
      "amount_usd": 250,
      "fill_price": 142.5
    }
  ],
  "quotes": [
    { "symbol": "SPY", "price_usd": 520.5, "source": "robinhood_mcp" }
  ],
  "errors": []
}
```

## Safety rules (binding)

- **Always** include `cursor_run_id` and `usage` on `POST /api/automation/runs` so CSV usage imports link to this lane.
- **Paper only** on this lane — use `simulated_buy` / `simulated_sell` only.
- Never `place_equity_order` unless `safety.trading_allowed` is true (should not happen on explorer).
- Respect `allowed_symbols`, caps, and cooldowns.
- Discovery picks must come from `candidate_pool` and stay within `max_per_run`.

## After weekly scout runs

Scout auto-promote should use `"update_lanes": false` so main lanes keep their strategy versions. Then point the explorer lane at the new strategy:

```bash
# Use strategy_version from scout auto-promote response
curl -sS -X PATCH "$API/api/admin/lanes/{EXPLORER_LANE_ID}" \
  -H "X-API-Key: $WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"strategy_version":"vN"}'
```

See [ticker-exploration-setup.md](./ticker-exploration-setup.md) for the full operator checklist.

## Related

- [ticker-exploration-setup.md](./ticker-exploration-setup.md) — one-time setup
- [ticker-scout-prompt.md](./ticker-scout-prompt.md) — weekly pool feeder
- [multi-lane-simulation.md](./multi-lane-simulation.md) — lane comparison
