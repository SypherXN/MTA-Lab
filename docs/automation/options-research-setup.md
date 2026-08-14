# Options Research Lane Setup

One automation + one API lane that papers **listed calls/puts** from a mix of option chains, tape, news, Reddit, and discovery. **Never live.** Other lanes stay equity-only.

| Piece | Name | Purpose |
|-------|------|---------|
| **Lane** | `options-research` | Isolated paper book (equity + option lots), plan **v6** |
| **Automation** | `mta-options` | Weekdays — research mix, paper options and occasional high-beta stock |

Compared vs SPY on the dashboard like the other challengers.

---

## What this lane can paper-trade

Defined-risk first:

- **Long call / long put** (`simulated_option_buy`) — cash falls by `premium × 100 × contracts`
- **Close long** (`simulated_option_sell`)
- **Cash-secured put** (`simulated_option_write` on a put) — needs `available_cash_usd >= strike × 100 × contracts`
- **Covered call** (`simulated_option_write` on a call) — only against **this lane's** paper shares
- **Buy back short** (`simulated_option_cover`)
- Speculative **equity** (`simulated_buy` / trim / stop / flatten) when the same research bar is met

Not in this slice: spreads, naked short calls, crypto, `place_option_order`.

---

## Phase 1 — Deploy repo artifacts

After `plans/v6.json` and the option book are on `main`:

```bash
ssh ubuntu@YOUR_VM_IP
cd ~/MTA-Lab
./scripts/mta update --force
sudo systemctl restart mta-lab-api
```

Confirm plan v6 exists after sync (the setup script also syncs):

```bash
curl -sS -X POST "$API/api/admin/plans/sync-from-repo" \
  -H "X-API-Key: $WRITE_KEY"
```

---

## Phase 2 — Bootstrap lane (one command)

On the VM (write key already in `api/.env`):

```bash
cd ~/MTA-Lab
set -a && source api/.env && set +a
export MTA_API_BASE=https://mta-api.matthewgtran.com
export MTA_WRITE_API_KEY="$MTA_WRITE_API_KEY"
./api/scripts/setup_options_lane.sh
```

The script:

1. Syncs plans from the repo (creates **v6**)
2. Forks a strategy with `options_enabled`, wider symbols, discovery, 12h cooldown
3. Creates lane **`options-research`** with **$5,000** paper cash (or updates it if it already exists)

Re-running is safe. Updating an existing lane does **not** reset its paper book.

---

## Phase 3 — Cursor automation

1. Create automation **`mta-options`**
2. Paste [options-prompt.md](./options-prompt.md)
3. Set `{OPTIONS_LANE_ID}` from the setup output
4. Schedule offset from other lanes (example: weekdays 12:00)
5. Tools: Robinhood MCP + HTTP to the API

On OCI micro with `MTA_SEQUENTIAL_LANES=true`, this automation can share a similar cron — it exits early when `lane_turn.granted` is false.

---

## Decision fields (options)

`symbol` is the **underlying** (must be in `allowed_symbols`). Also send:

| Field | Example |
|-------|---------|
| `option_right` | `call` or `put` |
| `strike` | `180` |
| `expiry` | `2026-08-21` |
| `contracts` | `1` (max `max_option_contracts`, usually 2) |
| `fill_price` | premium **per share** (e.g. `2.50` → $250 debit for 1 call) |

Import marks in `quotes[]` as `OPT:NVDA:2026-08-21:180:C` so the dashboard can mark the lot.

---

## Checks

| Check | Where |
|-------|--------|
| Lane exists | Dashboard → Lanes → `options-research` |
| Plan is v6 | Lane card / Agent Plans |
| Options enabled | `GET /api/automation/context?lane_id=N` → `safety.options_enabled` |
| Paper only | `safety.allowed_actions` includes `simulated_option_buy`, not live `buy` |
