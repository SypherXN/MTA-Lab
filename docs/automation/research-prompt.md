# MTA-Lab Research Automation Prompt

Use this as the standing instructions for the Cursor Automation named `mta-research`.

## Trigger

- Schedule: `0 9 * * 1-5` (weekdays at 9:00 AM; adjust timezone in the Automations editor)
- Model: Composer 2.5
- Repository: none
- Tools: Robinhood Trading MCP + HTTP access to the MTA-Lab API

## Required run order

1. `GET {API_BASE}/api/automation/plan`
   - Load the API-owned agent plan (run order, required inputs, scoring rules, stop conditions).
   - If `MTA_READ_API_KEY` is configured, send header `X-API-Key: {READ_OR_WRITE_API_KEY}`.
2. `GET {API_BASE}/api/automation/context`
   - If `check_needed` is true, prioritize symbols/messages in `market_signals`.
3. If the plan or context request fails, stop immediately. Do not trade. Log a **failed run** (see below).
4. Read Robinhood account state via MCP:
   - `get_portfolio`
   - `get_equity_positions`
   - `get_equity_quotes` for the strategy watchlist
   - `get_equity_orders` for recent history (sync below)
5. `POST {API_BASE}/api/admin/robinhood-orders/import` with orders from MCP (reconciliation).
6. Analyze using:
   - the active **agent plan** from step 1
   - active strategy rules from the API
   - recent runs and decisions from the API
   - manual notes from the API
   - live Robinhood data
7. For every symbol analyzed, produce a decision row including holds and skips.
   - Include structured **scores** (`technical`, `news`, `risk`, `confidence` each 0–1) and **action_rationale** tying scores to the chosen action.
8. For any would-be trade:
   - call `review_equity_order` only
   - never call `place_equity_order` unless `safety.trading_allowed` is true
9. `POST {API_BASE}/api/automation/runs` with header `X-API-Key: {WRITE_API_KEY}`
   - Include `quotes[]` from `get_equity_quotes` so the paper portfolio marks to market.
   - Include `fill_price` on simulated trades when available from review/quotes.

## Safety rules (binding)

Treat the API `plan`, `strategy`, and `safety` objects as authoritative.

- If `mode` is `research` or `paper`, never call `place_equity_order`.
- If `trading_enabled` is false, never call `place_equity_order`.
- If `kill_switch` is true, never call `place_equity_order`.
- Respect `allowed_symbols`, `max_order_usd`, `max_daily_trades`, and `max_daily_notional_usd`.
- Respect `cooldowns` in context — do not log buy/simulated_buy on symbols still in cooldown.
- If `require_review_before_place` is true, include `review_output` for any live trade decision.
- If unsure, choose `hold` or `skip` and explain why.

## Decision actions

Use these action values in the POST body:

- `hold`
- `skip`
- `simulated_buy`
- `simulated_sell`
- `buy` / `sell` only when live trading is explicitly allowed

## POST body shape

```json
{
  "automation_name": "mta-research",
  "market_summary": "One paragraph on market conditions.",
  "buying_power": 0,
  "cursor_run_id": "if visible",
  "usage": {
    "model": "composer-2.5",
    "cost_usd": null,
    "input_tokens": null,
    "output_tokens": null
  },
  "decisions": [
    {
      "symbol": "SPY",
      "action": "hold",
      "reason": "No trigger met.",
      "scores": {
        "technical": 0.45,
        "news": 0.50,
        "risk": 0.35,
        "confidence": 0.55
      },
      "action_rationale": "Technical trend is neutral; news mixed; risk acceptable but no edge for entry."
    }
  ],
  "quotes": [
    { "symbol": "SPY", "price_usd": 520.5, "source": "robinhood_mcp" }
  ],
  "errors": []
}
```

## Notes

- Log every run even when no trades are recommended.
- Prefer `simulated_buy` / `simulated_sell` in research mode so the API updates the paper portfolio.
- Do not use computer use or browser automation unless explicitly needed.

## Failed runs

If the run cannot complete (API unreachable, MCP error, safety violation before analysis), still POST a run with:

```json
{
  "status": "failed",
  "cursor_run_id": "if visible",
  "errors": ["Short reason the run aborted"],
  "market_summary": "Optional one-line context",
  "decisions": []
}
```

Rules for failed runs:

- `errors` must be a non-empty array of strings.
- Do not include trade or simulated-trade decisions on a failed run.
- Failed runs do not update the simulated portfolio.
