# Run Budget Guardrails

Per-automation and per-run-type cost limits so Cursor spend stays predictable.

## Budget layers

| Layer | Source | Action when exceeded |
|-------|--------|----------------------|
| Daily / monthly | `usage_budget` in context | Hold/skip only; note in `market_summary` |
| Per run type | `usage_budget.run_type_budget_usd` | Trim analysis depth before starting |
| Per run (logged) | API evaluates on `POST /api/automation/runs` | Sets `budget_exceeded` on run; creates alert |

## Expected budgets by run type

| `run_type` | Max cost (USD) | Max tokens |
|------------|------------------|------------|
| `daily_research` | 0.75 | 120,000 |
| `signal_response` | 0.15 | 30,000 |
| `post_market_review` | 0.50 | 80,000 |
| `reconciliation_only` | 0.10 | 20,000 |
| `live_preflight` | 1.00 | 150,000 |

## Agent checklist (before analyze)

1. Read `usage_budget` from `GET /api/automation/context`.
2. If `daily_exceeded` or `monthly_exceeded` → hold/skip only or POST failed run with reason.
3. Look up `run_type_budget_usd[run_type]` for this run's expected cap.
4. Use a cheaper model when the run type budget is tight (see [cost-aware-routing.md](../cost-aware-routing.md)).

## Logging usage (required when cost visible)

Include `usage` on every completed run:

```json
"usage": {
  "model": "composer-2.5",
  "cost_usd": 0.42,
  "input_tokens": 45000,
  "output_tokens": 8000
}
```

The API records `budget_exceeded`, `expected_budget_usd`, and `actual_cost_usd` on the run and returns `budget_check` in the POST response.

## Environment

Global caps (API):

- `MTA_DAILY_BUDGET_USD` (default 5.0)
- `MTA_MONTHLY_BUDGET_USD` (default 50.0)

Per-run-type caps are defined in `api/app/budget_service.py` (`RUN_TYPE_BUDGET_USD`, `RUN_TYPE_TOKEN_LIMITS`).

## Related

- [cost-aware-routing.md](../cost-aware-routing.md)
- [multi-cadence.md](./multi-cadence.md)
- [cost-tracking.md](../cost-tracking.md) — dashboard **Cost Dashboard** section
