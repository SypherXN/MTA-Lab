# Ticker Exploration Setup

Two automations + one API lane:

| Piece | Name | Purpose |
|-------|------|---------|
| **Scout** | `mta-ticker-scout` | Weekly — find 5–15 liquid tickers, import proposals, auto-promote into discovery pool |
| **Explorer** | `mta-explorer` | Weekdays — research anchors + up to `max_per_run` pool names on paper |
| **Lane** | `ticker-explorer` | Isolated paper portfolio, plan **v4**, explorer strategy rules |

Main lanes (1–3) stay unchanged. Scout grows the **active** strategy symbol list; only the explorer lane uses that strategy.

---

## Phase 1 — Deploy repo artifacts (you or CI)

After this doc and `plans/v4.json` are on `main`:

```bash
# On the VM
ssh ubuntu@YOUR_VM_IP
cd ~/MTA-Lab
./scripts/mta update
```

Or locally: `python3 api/scripts/sync_plans_from_repo.py`

Confirm plan v4 exists:

```bash
curl -sS "$API/api/automation/plan?lane_id=1" -H "X-API-Key: $WRITE_KEY" | head
# After setup, ?lane_id=EXPLORER_ID should return version v4
```

GitHub Pages picks up dashboard changes automatically on push.

---

## Phase 2 — Bootstrap explorer lane + strategy (one command)

From your machine (or VM) with write key:

```bash
export MTA_API_BASE=https://mta-api.matthewgtran.com
export MTA_WRITE_API_KEY=your-write-key

./api/scripts/setup_explorer_lane.sh
```

This script:

1. Forks the **active** strategy with explorer rules (wide `allowed_symbols`, small anchor watchlist, discovery enabled, `discovery_max_per_run: 8`)
2. Syncs plans from repo via API
3. Creates lane **`ticker-explorer`** on plan **v4** and the new strategy version
4. Prints `{EXPLORER_LANE_ID}` for your Cursor prompts

**Does not** change strategy versions on existing lanes.

Re-running is safe: it skips lane creation if `ticker-explorer` already exists.

---

## Phase 3 — Cursor automation: weekly scout

1. [cursor.com/automations](https://cursor.com/automations) → **New automation**
2. Name: **`mta-ticker-scout`**
3. Schedule: `0 14 * * 0` (Sunday — adjust timezone)
4. Model: Composer 2.5
5. Tools: Robinhood MCP + API HTTP
6. Paste [ticker-scout-prompt.md](./ticker-scout-prompt.md)
7. Replace `{API_BASE}` and `{WRITE_API_KEY}`
8. **Important:** in the auto-promote step use:

```json
{
  "min_score": 0.65,
  "max_symbols": 8,
  "enable_discovery": true,
  "discovery_max_per_run": 8,
  "update_lanes": false
}
```

9. After each scout run, update explorer lane strategy (script prints curl, or):

```bash
# strategy_version from auto-promote JSON response
curl -sS -X PATCH "$MTA_API_BASE/api/admin/lanes/EXPLORER_LANE_ID" \
  -H "X-API-Key: $MTA_WRITE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"strategy_version":"vN"}'
```

Optional: add that PATCH as a final step in the scout automation prompt.

---

## Phase 4 — Cursor automation: daily explorer

1. New automation: **`mta-explorer`**
2. Schedule: `30 10 * * 1-5` (offset from main `mta-research` cron)
3. Model: Composer 2.5
4. Tools: Robinhood MCP + API HTTP
5. Paste [explorer-prompt.md](./explorer-prompt.md)
6. Replace `{API_BASE}`, `{WRITE_API_KEY}`, `{EXPLORER_LANE_ID}` (from Phase 2 output)

On OCI micro with `MTA_SEQUENTIAL_LANES=true`, explorer and main automations can share similar crons — each exits early when `lane_turn.granted` is false.

---

## Phase 5 — Verify

| Check | How |
|-------|-----|
| Lane exists | Dashboard → **Lanes** → `ticker-explorer` |
| Plan v4 | `GET /api/automation/plan?lane_id=EXPLORER_ID` → `"version": "v4"` |
| Discovery on | `GET /api/automation/context?lane_id=EXPLORER_ID` → `symbol_discovery.enabled: true` |
| Scout proposals | `GET /api/admin/symbol-proposals?status=pending` |
| Explorer run | After first `mta-explorer` run → Decision Log shows **Lane** badge |
| Compare | Dashboard → Lane Comparison |

---

## Tuning

| Knob | Where | Suggestion |
|------|-------|------------|
| Names per day | Strategy `discovery_max_per_run` | 6–8 (max 10) |
| Pool size | Scout `max_symbols` | 8 per week |
| Anchor watchlist | Strategy `watchlist` | `SPY`, `QQQ` only |
| Trade caps | `max_daily_trades`, `max_order_usd` | Slightly higher than main lane if desired |
| Schedule | Cursor UI | Stagger scout (Sun) vs explorer (weekdays) |

Patch strategy (creates new version, becomes active):

```bash
curl -sS -X PATCH "$MTA_API_BASE/api/automation/strategy" \
  -H "X-API-Key: $MTA_WRITE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"rules":{"discovery_max_per_run":8,"symbol_discovery_enabled":true,...}}'
```

Then PATCH explorer lane to the returned `version`.

---

## Manual pool additions (without scout)

```bash
curl -sS -X POST "$MTA_API_BASE/api/admin/symbol-proposals/promote" \
  -H "X-API-Key: $MTA_WRITE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["NVDA","AMD","CRM"],
    "enable_discovery": true,
    "discovery_max_per_run": 8,
    "update_lanes": false
  }'
```

PATCH explorer lane to new `strategy_version` from the response.

---

## Related

- [explorer-prompt.md](./explorer-prompt.md)
- [ticker-scout-prompt.md](./ticker-scout-prompt.md)
- [multi-lane-simulation.md](./multi-lane-simulation.md)
- [agent-plans.md](../agent-plans.md)
