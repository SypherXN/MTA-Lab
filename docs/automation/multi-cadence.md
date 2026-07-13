# Multi-Cadence Market Checks

Run separate Cursor Automations instead of one large all-purpose job. Each schedule maps to an `run_type` on `POST /api/automation/runs`.

## Recommended schedules

| Automation | Cadence | `run_type` | Purpose |
|------------|---------|------------|---------|
| `mta-news` | Weekdays ~6:00 AM local (before research) | _(none — ingest only)_ | Shared headlines + earnings → `POST /api/admin/news/import` |
| `mta-daily-research` | Weekdays ~30 min after open | `daily_research` | Full research run: plan, context, market inputs, news, symbol memory, decisions |
| `mta-intraday-watch` | Hourly during market hours | `signal_response` | Lightweight watchlist check when `check_needed` signals exist |
| `mta-post-market` | Weekdays after close | `post_market_review` | Summarize day, sync orders, reconciliation focus |
| `mta-reconciliation` | Daily evening | `reconciliation_only` | Import Robinhood orders, run reconciliation alert check |
| `mta-live-preflight` | Before enabling live | `live_preflight` | Full preflight + live promotion workflow |

## Intraday watchlist run (minimal)

1. `GET /api/automation/context?lane_id={N}` — skip if no `check_needed` unless forced; respect `lane_turn` in sequential mode
2. `GET /api/automation/intervention/check`
3. Robinhood quotes for watchlist only
4. `POST /api/automation/runs` with `run_type: signal_response`

## Post-market run

1. Full order import via `POST /api/admin/robinhood-orders/import`
2. `POST /api/admin/alerts/reconciliation-check`
3. Summary run with `run_type: post_market_review`

## Cost discipline

- Use cheaper models on `signal_response` and `reconciliation_only` runs (see [cost-aware-routing.md](../cost-aware-routing.md)).
- Check `usage_budget` in context before expanding analysis depth.

## Related

- [research-prompt.md](./research-prompt.md) — run types table
- [news-ingestion-setup.md](./news-ingestion-setup.md) — VM RSS cron + `mta-news`
- [intervention-protocol.md](../intervention-protocol.md)
