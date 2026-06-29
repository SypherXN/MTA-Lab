# MTA-Lab API

FastAPI + SQLite backend for strategy context, automation run logs, and dashboard data.

## Local development

Requires Python 3.11+ in **WSL/Ubuntu** (this repo lives on WSL; do not use Windows Store `python3` from PowerShell).

```bash
cd api
chmod +x scripts/setup-dev.sh test.sh run.sh
./scripts/setup-dev.sh   # creates .venv, installs deps, copies .env
./test.sh                # run unit tests
./run.sh                 # start API on :8000
```

If `python3 -m venv` fails, install the venv package first:

```bash
sudo apt install -y python3-venv python3-pip
```

API: http://127.0.0.1:8000  
Docs: http://127.0.0.1:8000/docs

Default write key (change in `.env`): `dev-key-change-me`

Optional read key (`MTA_READ_API_KEY`): when set, all dashboard GET endpoints and automation read endpoints require `X-API-Key` (read key or write key). `/health` stays public.

## Backups

```bash
cd api
chmod +x scripts/backup-db.sh
./scripts/backup-db.sh
```

Writes timestamped copies to `data/backups/` (configurable via `MTA_BACKUP_DIR`, `MTA_BACKUP_KEEP`).

## Tests

```bash
cd api
./test.sh
```

Or manually:

```bash
cd api
source .venv/bin/activate
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Seed sample data

With the API running:

```bash
cd api
source .venv/bin/activate
python scripts/seed_sample_run.py
```

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | Health + SQLite connectivity (`503` if DB down) |
| GET | `/api/automation/plan` | Read* | Active agent plan (run order, inputs, scoring, stop conditions) |
| GET | `/api/automation/plans` | Read* | Plan version history (summaries) |
| GET | `/api/automation/plans/{version}` | Read* | Specific plan version snapshot |
| PATCH | `/api/automation/plan` | `X-API-Key` | Update plan (dedupes identical content; keeps last 20 versions) |
| GET | `/api/automation/context` | Read* | Strategy + history + safety + cooldowns + `check_needed` signals |
| GET | `/api/automation/preflight` | Read* | Live-trading readiness checklist |
| GET | `/api/automation/runs/{id}` | Read* | Single run with full decisions |
| POST | `/api/automation/runs` | `X-API-Key` | Log a run; optional `quotes[]` for mark-to-market |
| PATCH | `/api/automation/strategy` | `X-API-Key` | Update mode, trading flags, kill switch (bumps version on rule changes) |
| POST | `/api/automation/notes` | `X-API-Key` | Add manual context note |
| PATCH | `/api/automation/notes/{id}` | `X-API-Key` | Deactivate a manual note (`active: false`) |
| GET | `/api/dashboard/stats` | Read* | Summary metrics |
| GET | `/api/dashboard/runs` | Read* | Recent runs |
| GET | `/api/dashboard/decisions` | Read* | Decision log |
| GET | `/api/dashboard/portfolio` | Read* | Simulated portfolio (mark-to-market when quotes cached) |
| GET | `/api/dashboard/usage` | Read* | Cursor usage rows |
| GET | `/api/dashboard/orders` | Read* | Synced Robinhood orders + link status |
| GET | `/api/dashboard/reconciliation` | Read* | Order/decision reconciliation summary |
| GET | `/api/dashboard/quotes` | Read* | Cached quote prices |
| GET | `/api/dashboard/export` | Read* | CSV export (`type=all|runs|decisions`) |
| POST | `/api/admin/cursor-usage/import` | `X-API-Key` | Backfill Cursor usage (auto-links `cursor_run_id`) |
| POST | `/api/admin/portfolio/reset` | `X-API-Key` | Reset simulated cash/positions to defaults |
| POST | `/api/admin/quotes/import` | `X-API-Key` | Upsert quote cache for portfolio marks |
| POST | `/api/admin/robinhood-orders/import` | `X-API-Key` | Sync Robinhood orders; auto-link by `order_id` |
| POST | `/api/admin/webhooks/price-alert` | `X-API-Key` | Ingest external alert; sets `check_needed` in context |
| POST | `/api/admin/alerts/reconciliation-check` | `X-API-Key` | Dispatch reconciliation alert webhook if mismatches exist |

### Ops scripts

- `scripts/price_watcher.py` — import quotes and fire alerts on threshold moves (cron on OCI)
- `deploy/install.sh` — bootstrap API on a VM
- See `deploy/README.md` for systemd, nginx, and cron examples

\*Read auth applies only when `MTA_READ_API_KEY` is set in `.env`.

### Run status and safety

- `POST /api/automation/runs` accepts `status: "completed"` (default) or `status: "failed"`.
- Failed runs require a non-empty `errors` array and must not include trade/simulated-trade decisions.

## Decision scoring (AP-03)

Each decision in `POST /api/automation/runs` may include structured scores and rationale:

```json
{
  "symbol": "SPY",
  "action": "hold",
  "reason": "Short summary.",
  "scores": {
    "technical": 0.45,
    "news": 0.50,
    "risk": 0.35,
    "confidence": 0.55
  },
  "action_rationale": "How the scores led to this action."
}
```

All score fields are optional (0–1). Top-level `confidence` still works for backward compatibility. Scores appear in context, run detail, dashboard, and CSV export.
- Simulated trades are rejected (fail-closed) when they would violate strategy safety rules.
- `symbol_cooldown_hours` in strategy rules blocks repeat buys on the same symbol (exposed in context as `cooldowns`).

See [`../docs/ops-oci.md`](../docs/ops-oci.md) for OCI deployment and [`../docs/safety-gates.md`](../docs/safety-gates.md) for live trading controls.
