# MTA-Lab Reddit Research Automation Prompt

Use this as the standing instructions for the Cursor Automation named **`mta-reddit`**.

This lane is **paper-only** (`research` role). It ranks tickers from **public Reddit finance listings** (via the MTA API — not a logged-in scrape), then confirms with quotes before trading.

**Replace before enabling:**

| Placeholder | Example |
|-------------|---------|
| `{API_BASE}` | `https://mta-api.matthewgtran.com` |
| `{WRITE_API_KEY}` | Your `MTA_WRITE_API_KEY` |
| `{REDDIT_LANE_ID}` | Lane id from setup (e.g. `5`) |

Agent plan: **`v5`** (Reddit Research) — loaded via `GET /api/automation/plan?lane_id={REDDIT_LANE_ID}`.

## Trigger

- Schedule: `0 11 * * 1-5` (weekdays 11:00 AM — offset from other lanes; adjust timezone in Automations UI)
- Model: Composer 2.5
- Repository: none
- Tools: Robinhood Trading MCP + HTTP access to the MTA-Lab API

## Required run order

**Lane binding:** Append `?lane_id={REDDIT_LANE_ID}` on plan, context, memory, reddit, and discovery endpoints. Include `"lane_id": {REDDIT_LANE_ID}` on `POST /api/automation/runs`.

1. `GET {API_BASE}/api/automation/plan?lane_id={REDDIT_LANE_ID}`
2. `GET {API_BASE}/api/automation/context?lane_id={REDDIT_LANE_ID}`
   - If `lane_turn.granted` is **false**, exit with a short summary (sequential mode).
3. `GET {API_BASE}/api/automation/intervention/check`
4. Robinhood MCP: `get_portfolio`, `get_equity_positions`, `get_equity_quotes` for **open positions + SPY + QQQ + VIXY + top Reddit names**, `get_equity_orders`
4b. `POST {API_BASE}/api/admin/quotes/import` with all prices from step 4 (`X-API-Key: {WRITE_API_KEY}`).
5. `POST {API_BASE}/api/admin/robinhood-orders/import`
6. `GET {API_BASE}/api/automation/market-inputs?lane_id={REDDIT_LANE_ID}`
7. **Reddit research (required)**
   - `POST {API_BASE}/api/admin/reddit/ingest?lane_id={REDDIT_LANE_ID}` (`X-API-Key: {WRITE_API_KEY}`) — fetches public subreddit JSON and stores mention summaries.
   - `GET {API_BASE}/api/automation/reddit?lane_id={REDDIT_LANE_ID}` — ranked `mentions[]` and sample `posts[]`.
   - Do **not** log into Reddit, scrape private/NSFW communities, or use a browser for this step. The API is the research source.
   - If ingest/fetch returns `errors` and empty mentions, manage open positions only; do not force new buys.
8. `GET {API_BASE}/api/automation/news?source=reddit` plus per-symbol news for confirmation.
9. For **each** symbol you analyze (open positions first, then top mentions in `allowed_symbols`):
   - `GET {API_BASE}/api/automation/symbols/{SYMBOL}/memory?lane_id={REDDIT_LANE_ID}`
10. Analyze per plan **v5**. Produce a decision for every symbol analyzed.
11. Self-critique: Reddit citations, tape confirmation, position management, allowed_symbols, cooldowns, budget.
12. `POST {API_BASE}/api/automation/runs` with `X-API-Key: {WRITE_API_KEY}`

## POST body shape

```json
{
  "automation_name": "mta-reddit",
  "run_type": "daily_research",
  "lane_id": 5,
  "cursor_run_id": "bc-… (required — Cloud Agent ID from this run)",
  "usage": {
    "model": "composer-2.5",
    "cursor_run_id": "bc-… (same as above)",
    "cost_usd": null,
    "input_tokens": null,
    "output_tokens": null
  },
  "market_summary": "Reddit: NVDA 12 posts (sentiment +0.4); tape confirms. Trimmed TSLA after sentiment flipped.",
  "self_critique": "Cited threads; no buys without quote confirmation; managed open lots.",
  "decisions": [
    {
      "symbol": "NVDA",
      "action": "simulated_buy",
      "reason": "Clustered WSB + stocks mentions; quote holding up vs QQQ.",
      "scores": {
        "technical": 0.58,
        "news": 0.72,
        "risk": 0.45,
        "confidence": 0.62
      },
      "action_rationale": "Mention rollup NVDA 12 posts; top thread score 4k. Tape not hostile.",
      "amount_usd": 250,
      "fill_price": 142.5,
      "stop_price": 130,
      "target_price": 160
    }
  ],
  "quotes": [
    { "symbol": "SPY", "price_usd": 520.5, "source": "robinhood_mcp" }
  ],
  "errors": []
}
```

## Decision actions

Same paper vocabulary as other lanes: `hold`, `skip`, `simulated_buy`, `simulated_add`, `simulated_trim`, `simulated_take_profit`, `simulated_stop`, `simulated_flatten`. Review open lots every run.

## Safety rules (binding)

- **Always** include `cursor_run_id` and `usage` on `POST /api/automation/runs`.
- **Paper only** — never `place_equity_order` unless `safety.trading_allowed` is true.
- Trades only on `allowed_symbols`. Reddit tickers outside the list are skip/research-only.
- Do not buy a viral post against a dumping quote.
- Size $150–$300. Prefer liquid names.
- Public finance subs only (API default: wallstreetbets, stocks, investing, StockMarket, earnings).

## Related

- [reddit-research-setup.md](./reddit-research-setup.md) — one-time setup
- [research-prompt.md](./research-prompt.md) — shared action vocabulary
- [multi-lane-simulation.md](./multi-lane-simulation.md)
