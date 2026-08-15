# DTE Options Lane Setup (4-lane slice)

Paper-only experiment: **0DTE vs 1DTE**, **tape vs Reddit vs news** for names, and **tight vs loose** debit caps. Not live. Do not call `place_option_order`.

| Lane | Plan | Automation | Names from | DTE | Debit cap |
|------|------|------------|------------|-----|-----------|
| `odte-index` | v7 | `mta-odte-index` | SPY/QQQ tape | 0 (today ET) | $150 / 1 ct |
| `odte-reddit` | v8 | `mta-odte-reddit` | Reddit mentions | 0 | $150 / 1 ct |
| `1dte-news` | v9 | `mta-1dte-news` | RSS/earnings | 1 (next session) | $150 / 1 ct |
| `1dte-reddit-loose` | v10 | `mta-1dte-reddit` | Reddit mentions | 1 | $400 / 2 ct |

Each starts with **$5,000** paper cash (same as options-research). Compare **Lane % / vs SPY**, not dollar P&L vs the $1k equity lanes. Keep `options-research` (v6) running as the longer-dated control.

## Blocker

`mta-options` has been skipping because `get_option_quotes` returns **403**. These DTE lanes will do the same until quotes work **during US regular hours**. First useful test is a weekday RTH run, not overnight.

## Phase 1 — Deploy

```bash
ssh ubuntu@YOUR_VM_IP
cd ~/MTA-Lab
./scripts/mta update --force
sudo systemctl restart mta-lab-api
```

## Phase 2 — Create lanes

Requires `options-research` already on the API.

```bash
cd ~/MTA-Lab
set -a && source api/.env && set +a
export MTA_API_BASE=https://mta-api.matthewgtran.com
export MTA_WRITE_API_KEY="$MTA_WRITE_API_KEY"
./api/scripts/setup_dte_lanes.sh
```

The script syncs plans v7–v10, forks four strategy versions, creates or updates the four lanes, then restores the previous global active strategy so lane 1 is not left on a DTE rule set.

Re-running does **not** reset paper books.

## Phase 3 — Cursor automations

Create four automations. For each, paste [dte-options-prompt.md](./dte-options-prompt.md) and fill:

- `{LANE_ID}` from the setup table
- `{AUTOMATION_NAME}` / `{PLAN_VERSION}` from the table above
- Write key (same as other MTA jobs)

Suggested UTC crons (staggered past the 45-minute sequential lock; EDT = UTC−4):

| Automation | Cron UTC | Wall time (EDT) |
|------------|----------|-----------------|
| `mta-odte-index` | `15 15 * * 1-5` | 11:15 |
| `mta-odte-reddit` | `15 16 * * 1-5` | 12:15 |
| `mta-1dte-news` | `15 17 * * 1-5` | 13:15 |
| `mta-1dte-reddit` | `15 18 * * 1-5` | 14:15 |

Model: **Grok 4.6 xhigh**. Repository: none. Robinhood MCP on.

Manual **Run now** once during RTH before relying on cron.

## What success looks like

- `safety.min_option_dte` / `max_option_dte` present on context
- At least one `OPT:` quote imported
- A `simulated_option_buy` with expiry today (0DTE) or next session (1DTE), **or** honest skips when that expiry is missing
- Weekly/monthly expiries rejected by the API if posted anyway
- Paper book still isolated (no other-lane MSFT/SPY lots)

## Related

- [options-research-setup.md](./options-research-setup.md) — mixed longer-dated lane
- [multi-lane-simulation.md](./multi-lane-simulation.md) — sequential lock
