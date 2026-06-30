# MTA-Lab Research Automation Prompt

Use this as the standing instructions for the Cursor Automation named `mta-research`.

## Trigger

- Schedule: `0 9 * * 1-5` (weekdays at 9:00 AM; adjust timezone in the Automations editor)
- Model: Composer 2.5
- Repository: none
- Tools: Robinhood Trading MCP + HTTP access to the MTA-Lab API

## Required run order

**Multi-lane:** When `MTA_LANE_ID` is set (or your automation targets a specific approach), append `?lane_id={N}` to context/plan/memory endpoints and include `"lane_id": N` on `POST /api/automation/runs`. See [multi-lane-simulation.md](multi-lane-simulation.md).

1. `GET {API_BASE}/api/automation/plan?lane_id={N}` (optional `lane_id`)
   - Load the API-owned agent plan (run order, required inputs, scoring rules, stop conditions).
   - If `MTA_READ_API_KEY` is configured, send header `X-API-Key: {READ_OR_WRITE_API_KEY}`.
2. `GET {API_BASE}/api/automation/context?lane_id={N}` (optional `lane_id`)
   - If `check_needed` is true, prioritize symbols/messages in `market_signals`.
   - Review `freshness_checks`: if `ready_for_analysis` is false, do not open new positions; hold/skip and cite `warnings` in `market_summary`.
   - Review `intervention_status`: if `intervention_required` is true, follow [intervention protocol](../intervention-protocol.md) (critical → failed run; high → hold/skip only).
   - Note `recent_news` and `market_input_bundle` preview when present.
3. `GET {API_BASE}/api/automation/intervention/check` (recommended)
   - Confirm no critical triggers before gathering market data.
4. If the plan, context, or critical intervention check fails, stop immediately. Do not trade. Log a **failed run** (see below).
5. Read Robinhood account state via MCP:
   - `get_portfolio`
   - `get_equity_positions`
   - `get_equity_quotes` for the strategy watchlist **plus** index symbols (SPY, QQQ) and volatility proxies (VIX or VIXY when available)
   - `get_equity_orders` for recent history (sync below)
6. `POST {API_BASE}/api/admin/robinhood-orders/import` with orders from MCP (reconciliation).
   - Include all quotes from step 5 in the run `quotes[]` when logging (step 13).
7. `GET {API_BASE}/api/automation/market-inputs` (required)
   - Review the checklist: watchlist quotes, index state, orders synced, positions, freshness.
   - If `ready` is false, hold/skip only and explain missing items in `market_summary`.
   - Use `movers`, `index_quotes`, and `volatility_quotes` in your market read.
8. **News and event intake** (required)
   - Read `recent_news` from context and `GET {API_BASE}/api/automation/news?symbol={SYMBOL}` per symbol when needed.
   - When you find material headlines, earnings, or macro items from external sources, ingest summaries via `POST {API_BASE}/api/admin/news/import` (write key).
   - Use news in `news` scores and `action_rationale`; do not trade on stale or missing news without noting the gap.
9. For **each symbol** you will analyze, call `GET {API_BASE}/api/automation/symbols/{SYMBOL}/memory?lane_id={N}` (required).
   - Use prior decisions, cooldowns, position, P&L, notes, signals, and `recent_news` in your analysis.
   - If memory fetch fails for a symbol, skip that symbol and note the error.
10. Analyze using:
   - the active **agent plan** from step 1
   - active strategy rules from the API
   - market input bundle from step 7
   - news context from step 8
   - recent runs and decisions from the API
   - manual notes from the API
   - live Robinhood data
   - symbol memory from step 9
11. For every symbol analyzed, produce a decision row including holds and skips.
    - Include structured **scores** (`technical`, `news`, `risk`, `confidence` each 0–1) and **action_rationale** tying scores to the chosen action.
12. For any would-be trade:
    - call `review_equity_order` only
    - never call `place_equity_order` unless `safety.trading_allowed` is true
13. **Self-critique** (required before submit)
    - Verify each decision against: strategy rules, safety caps, cooldowns, freshness warnings, symbol memory, and score consistency.
    - Downgrade to hold/skip if any check fails.
    - Write a short paragraph summary in the `self_critique` field on the run POST body.
14. `POST {API_BASE}/api/automation/runs` with header `X-API-Key: {WRITE_API_KEY}`
    - Set `run_type` to match this automation's purpose (see **Run types** below). Default: `daily_research`.
    - Include `self_critique` (required when logging decisions on a completed run).
    - Include `quotes[]` from `get_equity_quotes` so the paper portfolio marks to market.
    - Include `fill_price` on simulated trades when available from review/quotes.

## Run types

Use the `run_type` field on `POST /api/automation/runs`. Valid values (also in `GET /api/automation/context` → `valid_run_types`):

| run_type | When to use |
|----------|-------------|
| `daily_research` | Scheduled weekday research run (default) |
| `signal_response` | Triggered by `check_needed` / price alert |
| `post_market_review` | After-hours reconciliation and summary |
| `reconciliation_only` | Order sync and mismatch check only |
| `live_preflight` | Pre-live checklist before enabling trading |

See [multi-cadence.md](../multi-cadence.md) for separate automation schedules per run type.

Before analyzing a symbol in depth, **must** call `GET {API_BASE}/api/automation/symbols/{SYMBOL}/memory` for prior actions, cooldowns, P&L, notes, signals, and decision history. Reference this history in each decision's `reason` or `action_rationale`.

## Safety rules (binding)

Treat the API `plan`, `strategy`, and `safety` objects as authoritative.

- If `mode` is `research` or `paper`, never call `place_equity_order`.
- If `trading_enabled` is false, never call `place_equity_order`.
- If `kill_switch` is true, never call `place_equity_order`.
- Respect `allowed_symbols`, `max_order_usd`, `max_daily_trades`, and `max_daily_notional_usd`.
- Respect `cooldowns` in context — do not log buy/simulated_buy on symbols still in cooldown.
- If `require_review_before_place` is true, include `review_output` for any live trade decision.
- If unsure, choose `hold` or `skip` and explain why.

## Simulation discipline (research mode)

Default mode is research with fake-money tracking. See [simulation-discipline.md](../simulation-discipline.md).

- Use `simulated_buy` / `simulated_sell` (not `buy`/`sell`) so the API updates the paper portfolio.
- Include `amount_usd` and `fill_price` on every simulated trade when quotes are available.
- Failed runs must not include simulated or live trade decisions.
- Portfolio snapshots and equity curves come from completed runs only.
- Live promotion requires preflight + token approval (`GET /api/automation/live-promotion/status`).

## Run budget guardrails

Before expanding analysis, check `usage_budget` in context. See [run-budget-guardrails.md](./run-budget-guardrails.md).

- If `usage_budget.budget_ok` is false → hold/skip only; explain in `market_summary`.
- Match your `run_type` to `usage_budget.run_type_budget_usd` — do not exceed that run's expected cost.
- Always log `usage.cost_usd` and token counts when visible from Cursor billing.
- If the run cost exceeds the run-type budget, the API flags `budget_exceeded` and creates an alert — mention it in `self_critique`.

## Cost-aware routing

Check `usage_budget` in context before expanding run depth. See [cost-aware-routing.md](../cost-aware-routing.md).

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
  "run_type": "daily_research",
  "market_summary": "One paragraph on market conditions.",
  "self_critique": "Checked strategy/safety/cooldowns/freshness/memory; all holds appropriate.",
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
- `self_critique` is not required on failed runs.
