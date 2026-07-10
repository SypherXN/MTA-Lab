# Multi-Lane Simulation

Run multiple strategy/plan approaches in parallel, each with an isolated paper portfolio, then compare performance before promoting a challenger to live.

## Concepts

| Term | Meaning |
|------|---------|
| **Lane** | A simulation track with its own `strategy_version`, `plan_version`, cash, positions, snapshots, and symbol memory |
| **Primary lane** | Default lane (`id=1`, name `primary`) — used when `lane_id` is omitted |
| **Research** | Paper-only lane for experiments |
| **Shadow** | Paper lane running alongside live for head-to-head comparison |
| **Live** | The deployed lane — only this lane may submit real `buy`/`sell` orders |

Each lane is bound to a **strategy version + plan version** pair at creation time. Separate Cursor automations post runs with different `lane_id` values.

## API workflow

### 1. Create lanes (admin)

```bash
curl -X POST "$API/api/admin/lanes" \
  -H "X-API-Key: $WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "conservative-v2",
    "strategy_version": "v2",
    "plan_version": "v1",
    "lane_role": "shadow"
  }'
```

### 2. Agent run (per automation)

```text
GET /api/automation/context?lane_id=2
GET /api/automation/plan?lane_id=2
GET /api/automation/symbols/{symbol}/memory?lane_id=2
POST /api/automation/runs  { "lane_id": 2, ... }
```

`lane_id` defaults to the primary lane when omitted.

### 3. Compare lanes

```bash
curl "$API/api/dashboard/lanes/compare?lane_ids=1,2,3"
```

Per-lane metrics include **lane-scoped** `equity_change_usd` from snapshots (not the global curve).

### 4. Promote challenger to live

Requires preflight pass:

```bash
curl -X POST "$API/api/admin/lanes/2/promote-to-live" \
  -H "X-API-Key: $WRITE_KEY"
```

Demotes the current live lane to `shadow`, sets the target to `live`, and activates live trading with the promoted lane's strategy rules.

## Cursor Automation setup

Run **N automations** on the same schedule, each with a different lane:

| Automation | Env / prompt | Lane |
|------------|--------------|------|
| Research baseline | `MTA_LANE_ID=1` | primary |
| Challenger A | `MTA_LANE_ID=2` | shadow |
| Challenger B | `MTA_LANE_ID=3` | shadow |

Document `lane_id` in each automation's prompt and pass it on every context fetch and run POST.

**During live deployment:** keep one automation on the live lane; run shadow automations in parallel with the same market-input steps but never submit live orders unless `lane_role=live`.

## Dashboard

- **Live Money Track** — stitched equity across every lane that has been live; timeline of live stints; former live lanes keep full history when demoted to shadow
- **Simulation Lanes** — card view with role badges (live / shadow / research)
- **Lane Comparison** — head-to-head per-lane metrics (correct equity per lane)
- **Paper Portfolio Comparison** — overlay equity curves for challengers
- **Portfolio selector** — view any lane's cash/positions and snapshots

`GET /api/dashboard/lanes/live-history` returns combined live stint history for dashboards and reporting.
- **Equity Curve** — multi-lane overlay (checkbox per lane)
- **Runs table** — lane name + role badge

## Storage notes

- Each lane has isolated `simulated_cash`, `simulated_positions`, `portfolio_snapshots`, and `symbol_memory_summaries`
- Cooldowns and daily trade caps are **per lane**
- Quote cache and news remain global (shared market data)

## Recommended practice

1. Start with primary lane in research until you have a baseline
2. Create shadow lanes for each strategy/plan variant you want to test
3. Run parallel automations for 1–2 weeks; compare via `/api/dashboard/lanes/compare`
4. Promote the best shadow lane to live when preflight passes
5. Keep other shadows running to monitor challengers against live performance
