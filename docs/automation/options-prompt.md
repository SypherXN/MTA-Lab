# MTA-Lab Options Research Automation Prompt

Use this as the standing instructions for the Cursor Automation named **`mta-options`**.

This lane is **paper-only** (`research` role). It takes **defined-risk listed options** (and occasional high-beta stock) from a **mix** of option chains, tape, news, Reddit, and discovery.

**Replace before enabling:**

| Placeholder | Example |
|-------------|---------|
| `{API_BASE}` | `https://mta-api.matthewgtran.com` |
| `{WRITE_API_KEY}` | Your `MTA_WRITE_API_KEY` |
| `{OPTIONS_LANE_ID}` | Lane id from setup (e.g. `6`) |

Agent plan: **`v6`** (Options Research) — loaded via `GET /api/automation/plan?lane_id={OPTIONS_LANE_ID}`.

## Trigger

- Schedule: `0 12 * * 1-5` (weekdays 12:00 — offset from other lanes; adjust timezone in Automations UI)
- Model: Composer 2.5
- Repository: none
- Tools: Robinhood Trading MCP + HTTP access to the MTA-Lab API

## Required run order

**Lane binding:** Append `?lane_id={OPTIONS_LANE_ID}` on plan, context, memory, reddit, news, discovery, and market-inputs. Include `"lane_id": {OPTIONS_LANE_ID}` on `POST /api/automation/runs`.

1. `GET {API_BASE}/api/automation/plan?lane_id={OPTIONS_LANE_ID}`
2. `GET {API_BASE}/api/automation/context?lane_id={OPTIONS_LANE_ID}`
   - If `lane_turn.granted` is **false**, exit with a short summary (sequential mode).
   - Confirm `safety.options_enabled` is true. Use `simulated_portfolio` as the **only** book you manage (`available_cash_usd`, `reserved_usd`, option lots).
3. `GET {API_BASE}/api/automation/intervention/check`
4. Robinhood MCP:
   - **`get_accounts` first**, then pass `account_number` on later calls.
   - `get_portfolio`, `get_equity_quotes` for **this lane's open underlyings + SPY + QQQ + VIXY + shortlist**
   - `get_equity_positions` / `get_option_positions` are **live RH context only** — do not hold/trim them as if they were this lane.
   - `get_equity_orders` (with `account_number`)
4b. `POST {API_BASE}/api/admin/quotes/import` with equity prices (`X-API-Key: {WRITE_API_KEY}`).
5. `POST {API_BASE}/api/admin/robinhood-orders/import`
6. `GET {API_BASE}/api/automation/market-inputs?lane_id={OPTIONS_LANE_ID}`
7. Reddit (one of several sources):
   - `POST {API_BASE}/api/admin/reddit/ingest?lane_id={OPTIONS_LANE_ID}`
   - `GET {API_BASE}/api/automation/reddit?lane_id={OPTIONS_LANE_ID}`
8. `GET {API_BASE}/api/automation/news` (and `?source=reddit` if useful) for confirmation.
9. Optional: `GET {API_BASE}/api/automation/discovery/candidates?lane_id={OPTIONS_LANE_ID}`
10. For shortlisted names in `allowed_symbols`: MCP `get_option_chains`, `get_option_instruments`, `get_option_quotes` (and historicals when the structure matters).
11. For **each** symbol you analyze (open lots first):
    `GET {API_BASE}/api/automation/symbols/{SYMBOL}/memory?lane_id={OPTIONS_LANE_ID}`
12. Analyze per plan **v6**. Produce a decision for every symbol analyzed.
13. You may `review_option_order` / `review_equity_order`. **Never** `place_option_order` or `place_equity_order`.
14. Self-critique: two-source research, option fields, no live place, paper book ≠ live RH, lots managed.
15. `POST {API_BASE}/api/automation/runs` with `X-API-Key: {WRITE_API_KEY}`

## POST body shape

```json
{
  "automation_name": "mta-options",
  "run_type": "daily_research",
  "lane_id": 6,
  "cursor_run_id": "bc-… (required — Cloud Agent ID from this run)",
  "usage": {
    "model": "composer-2.5",
    "cursor_run_id": "bc-… (same as above)",
    "cost_usd": null,
    "input_tokens": null,
    "output_tokens": null
  },
  "market_summary": "Mixed tape. NVDA chain bid/ask tight; Reddit + earnings confirmation. Bought 1x 180C.",
  "self_critique": "Two sources cited; paper book only; no place_option_order; managed open lots.",
  "decisions": [
    {
      "symbol": "NVDA",
      "action": "simulated_option_buy",
      "reason": "Defined-risk call: tape + chain + news aligned.",
      "scores": {
        "technical": 0.62,
        "news": 0.58,
        "risk": 0.55,
        "confidence": 0.60
      },
      "action_rationale": "News: named headline. Chain: 180C weekly bid/ask 2.40/2.60. Tape holding vs QQQ.",
      "option_right": "call",
      "strike": 180,
      "expiry": "2026-08-21",
      "contracts": 1,
      "fill_price": 2.50,
      "amount_usd": 250
    }
  ],
  "quotes": [
    { "symbol": "NVDA", "price_usd": 175.2, "source": "robinhood_mcp" },
    { "symbol": "OPT:NVDA:2026-08-21:180:C", "price_usd": 2.50, "source": "robinhood_mcp" },
    { "symbol": "SPY", "price_usd": 520.5, "source": "robinhood_mcp" }
  ],
  "errors": []
}
```

## Decision actions

**Equity (same as other lanes):** `hold`, `skip`, `simulated_buy`, `simulated_add`, `simulated_trim`, `simulated_take_profit`, `simulated_stop`, `simulated_flatten`.

**Options (this lane only):**

| Action | Meaning |
|--------|---------|
| `simulated_option_buy` | Buy to open long call or put (debit = premium × 100 × contracts) |
| `simulated_option_sell` | Sell to close a long |
| `simulated_option_write` | Sell to open: **CSP** if put, **covered call** if call and you hold paper shares |
| `simulated_option_cover` | Buy to close a short |

Omit `contracts` on a close to flatten that contract. `fill_price` is **premium per share**.

## Safety rules (binding)

- **Always** include `cursor_run_id` and `usage` on `POST /api/automation/runs`.
- **Paper only** — never `place_option_order` or `place_equity_order`.
- Trades only on `allowed_symbols` (underlying).
- New entries need **two** sources (chain/tape/news/Reddit/discovery). Cite them.
- Default to **debit** options. Naked short calls are impossible on this API and forbidden in the prompt.
- CSP only when `strike × 100 × contracts` fits `available_cash_usd` and `max_csp_notional_usd`.
- Prefer 1 contract; never more than `max_option_contracts`.
- Do not confuse live Robinhood positions with this lane's `simulated_portfolio`.

## Related

- [options-research-setup.md](./options-research-setup.md) — one-time setup
- [research-prompt.md](./research-prompt.md) — shared equity vocabulary
- [multi-lane-simulation.md](./multi-lane-simulation.md)
