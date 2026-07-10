# Cost-Aware Model Routing

Use cheaper Cursor models for routine checks and reserve stronger models for high-impact decisions.

## Routing matrix

| Run type | Recommended model tier | Rationale |
|----------|------------------------|-----------|
| `signal_response` | Fast / cheap | Short watchlist pass |
| `reconciliation_only` | Fast / cheap | Import + mismatch check |
| `daily_research` | Standard | Full analysis with self-critique |
| `post_market_review` | Standard | Summaries and reconciliation |
| `live_preflight` | Strong | Live promotion and safety validation |

## Before each run

1. Read `usage_budget` from `GET /api/automation/context`.
2. If `daily_exceeded` or `monthly_exceeded`, use hold/skip-only depth or abort with failed run.
3. Log actual model and cost in `usage` on the run POST.

## Prompt rules

- Do not re-fetch full symbol memory for symbols not on the watchlist during intraday runs.
- Skip news deep-dive on `reconciliation_only` runs.
- Escalate to stronger model only when: live mode, intervention high severity, or large simulated drawdown alert.

## Environment

Configure budgets on the API:

- `MTA_DAILY_BUDGET_USD` (default 5.0)
- `MTA_MONTHLY_BUDGET_USD` (default 50.0)

Dashboard **Cost Dashboard** and **Cursor Usage** sections visualize spend. See [cost-tracking.md](../cost-tracking.md).

Budget state is exposed as `usage_budget` in automation context and triggers `budget_exceeded` alerts via AP-11 routing.

## Related

- [multi-cadence.md](./multi-cadence.md)
- [cost-tracking.md](../cost-tracking.md)
