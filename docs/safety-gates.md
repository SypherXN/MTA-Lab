# Safety Gates

Live trading is blocked unless all of the following are true:

| Gate | Requirement |
|------|-------------|
| Mode | `live` |
| Trading enabled | `true` |
| Kill switch | `false` |
| Symbol allowlist | decision symbol in `allowed_symbols` |
| Order cap | `amount_usd <= max_order_usd` |
| Daily trade cap | run stays within `max_daily_trades` |
| Daily notional cap | run stays within `max_daily_notional_usd` |
| Review required | live actions include `review_output` when configured |

## Fail-closed behavior

- Research and paper modes reject live `buy` / `sell` decisions at the API layer.
- Missing or ambiguous safety fields should cause the automation to hold/skip rather than trade.
- If context fetch fails, the automation must not trade.

## Updating strategy flags

Strategy data lives in the `strategies` table. The seeded default is research mode with `trading_enabled=false`.

**Dashboard:** use the **Safety Controls** card (`PATCH /api/dashboard/strategy`) — requires dashboard login or write API key; creates a new strategy version on change.

**API (automation write key):**

```bash
curl -X PATCH https://your-api.example.com/api/automation/strategy \
  -H "X-API-Key: YOUR_WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode": "live", "trading_enabled": true, "kill_switch": false}'
```

To go live manually via SQL (after validation):

```sql
UPDATE strategies SET is_active = 0;
INSERT INTO strategies (version, name, mode, trading_enabled, kill_switch, rules_json, is_active)
VALUES (
  'v2-live',
  'Live Strategy',
  'live',
  1,
  0,
  '{"allowed_symbols":["SPY","QQQ"],"max_order_usd":250,"max_daily_trades":2,"max_daily_notional_usd":500,"require_review_before_place":true,"watchlist":["SPY","QQQ"]}',
  1
);
```

Emergency stop via API:

```bash
curl -X PATCH https://your-api.example.com/api/automation/strategy \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"kill_switch": true}'
```

Or via SQL:

```sql
UPDATE strategies SET kill_switch = 1 WHERE is_active = 1;
```
