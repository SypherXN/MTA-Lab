# MTA-Lab DTE Options Automation Prompt

Standing instructions for one of the four **paper** DTE lanes. Never live.

**Replace before enabling:**

| Placeholder | Example |
|-------------|---------|
| `{API_BASE}` | `https://mta-api.matthewgtran.com` |
| `{WRITE_API_KEY}` | Your `MTA_WRITE_API_KEY` |
| `{LANE_ID}` | From `setup_dte_lanes.sh` output |
| `{AUTOMATION_NAME}` | `mta-odte-index` / `mta-odte-reddit` / `mta-1dte-news` / `mta-1dte-reddit` |
| `{PLAN_VERSION}` | `v7` / `v8` / `v9` / `v10` |

| Automation | Plan | Name source | DTE | Safety |
|------------|------|-------------|-----|--------|
| `mta-odte-index` | v7 | SPY/QQQ tape only | 0 (today ET) | $150 debit, 1 contract |
| `mta-odte-reddit` | v8 | Reddit mentions in allowed_symbols | 0 | $150 / 1 |
| `mta-1dte-news` | v9 | RSS/earnings news | 1 (next session; Fri→Mon) | $150 / 1 |
| `mta-1dte-reddit` | v10 | Reddit mentions | 1 | $400 / 2 contracts |

## Trigger

- Cron UTC from setup output (after US cash open; sequential lock 45 min — stagger)
- Model: **Grok 4.6 xhigh**
- Repository: none
- Tools: Robinhood Trading MCP + HTTP to the MTA-Lab API

## Required run order

Append `?lane_id={LANE_ID}` on plan, context, memory, reddit, news, discovery, market-inputs. Include `"lane_id": {LANE_ID}` on `POST /api/automation/runs`. Header `X-API-Key: {WRITE_API_KEY}` on MTA writes.

1. `GET {API_BASE}/api/automation/plan?lane_id={LANE_ID}`
2. `GET {API_BASE}/api/automation/context?lane_id={LANE_ID}`
   - If `lane_turn.granted` is **false**, exit with a short summary.
   - Confirm `safety.options_enabled`, `min_option_dte`, `max_option_dte`, `max_option_debit_usd`.
   - Use `simulated_portfolio` as the only book.
3. `GET {API_BASE}/api/automation/intervention/check`
4. Robinhood MCP: `get_accounts` first. Quote SPY/QQQ/VIXY + open underlyings + shortlist.
   - Live RH positions are **not** this book.
5. `POST {API_BASE}/api/admin/quotes/import` (equity marks).
6. `POST {API_BASE}/api/admin/robinhood-orders/import`
7. `GET {API_BASE}/api/automation/market-inputs?lane_id={LANE_ID}`
8. **Name source (this lane only):**
   - **v7:** do not ingest Reddit for names. Analyze SPY and QQQ only.
   - **v8 / v10:** `POST {API_BASE}/api/admin/reddit/ingest?lane_id={LANE_ID}` then `GET {API_BASE}/api/automation/reddit?lane_id={LANE_ID}`. Rank mentions in `allowed_symbols`.
   - **v9:** `GET {API_BASE}/api/automation/news` (and context `recent_news`). Rank tickers from headlines/earnings in `allowed_symbols`. Do not use Reddit as the name source.
9. Optional: `GET {API_BASE}/api/automation/discovery/candidates?lane_id={LANE_ID}`
10. For each shortlisted underlying: `get_option_chains` / `get_option_quotes` for the **DTE expiry only**.
    - 0DTE = today's date in America/New_York
    - 1DTE = next session (skip weekend)
    - Import `OPT:SPY:YYYY-MM-DD:STRIKE:C` (mid or last) with the equity quotes.
    - If quotes 403 or the chain has no that expiry, **skip** — do not buy a weekly.
11. Memory: `GET {API_BASE}/api/automation/symbols/{SYMBOL}/memory?lane_id={LANE_ID}`
12. Analyze per plan `{PLAN_VERSION}`. Decision for every name analyzed. Debit-only (`simulated_option_buy` / `simulated_option_sell`). No writes, no new equity.
13. Never `place_option_order` or `place_equity_order`.
14. `POST {API_BASE}/api/automation/runs`

## POST body

```json
{
  "automation_name": "{AUTOMATION_NAME}",
  "run_type": "daily_research",
  "lane_id": {LANE_ID},
  "cursor_run_id": "bc-…",
  "usage": {
    "model": "cursor-grok-4.6-xhigh",
    "cursor_run_id": "bc-…",
    "cost_usd": null,
    "input_tokens": null,
    "output_tokens": null
  },
  "market_summary": "RTH. 0DTE SPY 560C bid/ask 1.20/1.30. Bought 1x.",
  "self_critique": "DTE window respected; name source followed; paper only; no place_option_order.",
  "decisions": [
    {
      "symbol": "SPY",
      "action": "simulated_option_buy",
      "reason": "Defined-risk 0DTE call: tape + fillable chain.",
      "scores": { "technical": 0.62, "news": 0.40, "risk": 0.45, "confidence": 0.58 },
      "action_rationale": "Tape: SPY RSI 64 holding VWAP. Chain: today 560C 1.20/1.30.",
      "option_right": "call",
      "strike": 560,
      "expiry": "2026-08-15",
      "contracts": 1,
      "fill_price": 1.25,
      "amount_usd": 125
    }
  ],
  "quotes": [
    { "symbol": "SPY", "price_usd": 778.5, "source": "robinhood_mcp" },
    { "symbol": "OPT:SPY:2026-08-15:560:C", "price_usd": 1.25, "source": "robinhood_mcp" }
  ],
  "errors": []
}
```

## Binding rules

- Paper only. `cursor_run_id` + `usage` required.
- Expiry must match `min_option_dte` / `max_option_dte` or the API will reject the run.
- Debit must fit `max_option_debit_usd`.
- Two sources as the plan for this version requires.
- Do not confuse live Robinhood or other-lane lots with this book.

## Related

- [dte-options-setup.md](./dte-options-setup.md)
- [options-prompt.md](./options-prompt.md) — longer-dated mixed lane (v6)
