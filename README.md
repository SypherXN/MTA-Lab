# MTA-Lab

Market Test Agent Lab — an auditable agentic trading system for research-first market testing.

Scheduled **Cursor Automations** use **Robinhood MCP** for quotes, portfolio data, and order review. Strategy, agent plans, multi-lane simulation, run logs, and portfolio state live in a small **OCI-hosted API**. A **GitHub Pages** dashboard reads from that API.

## Architecture

```text
Cursor Automation (schedule, per lane)
  → GET  /api/automation/plan?lane_id=N
  → GET  /api/automation/context?lane_id=N
  → Robinhood MCP (read + review_equity_order)
  → POST /api/automation/runs { lane_id, ... }

GitHub repo plans/*.json  →  sync  →  API agent_plans table
GitHub Pages dashboard    →  GET   /api/dashboard/* + /api/automation/plan
```

See [`docs/PLAN.md`](docs/PLAN.md) for design goals and [`docs/automation/multi-lane-simulation.md`](docs/automation/multi-lane-simulation.md) for lane model.

## Quick start (API)

Requires Python 3.11+ in **WSL/Ubuntu** when developing on Windows.

```bash
cd api
chmod +x scripts/setup-dev.sh test.sh run.sh
./scripts/setup-dev.sh    # venv, deps, .env
./run.sh                  # http://127.0.0.1:8000
./test.sh                 # unit tests
```

Or manually:

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Default write key (change in `.env`): `dev-key-change-me`

## VM operations (OCI)

After clone on your micro VM:

```bash
cd ~/MTA-Lab/api
./deploy/install.sh
# edit .env
./deploy/install-service.sh    # auto-start on boot + restart on crash
./deploy/install-cron.sh       # optional: backup + retention cron
./scripts/mta-ctl.sh status
./scripts/mta-ctl.sh update    # after git pull
```

From repo root: `./scripts/mta status`, `./scripts/mta update`, `./scripts/mta logs -f`

See [`api/deploy/README.md`](api/deploy/README.md).

## Quick start (dashboard)

```bash
cd dashboard
cp config.example.js config.js
# edit API_BASE_URL, optional PLANS_REPO_URL for GitHub edit links
python3 -m http.server 8080
```

Open **http://localhost:8080** with the API on port 8000.

- Local dev: leave `MTA_DASHBOARD_PASSWORD` empty — no login required.
- Add `http://localhost:8080` and `http://127.0.0.1:8080` to `MTA_CORS_ORIGINS` in `api/.env`.
- Hard refresh after CSS/JS changes (`Ctrl+Shift+R`).

See [`dashboard/README.md`](dashboard/README.md) for UI sections and configuration.

## Agent plans (GitHub → API)

Plan JSON lives in [`plans/`](plans/) in this repo. The dashboard shows read-only plan details per lane; edits happen in GitHub.

After pulling plan changes on the server:

```bash
python3 api/scripts/sync_plans_from_repo.py
# or: POST /api/admin/plans/sync-from-repo (write key)
```

See [`docs/agent-plans.md`](docs/agent-plans.md).

## Repo layout

| Path | Purpose |
|------|---------|
| [`api/`](api/) | FastAPI service + SQLite |
| [`dashboard/`](dashboard/) | Static GitHub Pages frontend |
| [`plans/`](plans/) | Agent plan JSON (source of truth in git) |
| [`docs/automation/`](docs/automation/) | Cursor Automation prompts and setup |
| [`docs/agent-plans.md`](docs/agent-plans.md) | Plan file format and sync workflow |
| [`docs/safety-gates.md`](docs/safety-gates.md) | Live trading safety rules |
| [`docs/cost-tracking.md`](docs/cost-tracking.md) | Cursor usage reconciliation |
| [`docs/ops-oci.md`](docs/ops-oci.md) | OCI deployment, retention, sequential lanes |

## API overview

| Area | Key endpoints |
|------|----------------|
| Health | `GET /health`, `GET /metrics` |
| Auth | `GET /api/auth/status`, `POST /api/auth/login` |
| Automation | `GET /api/automation/context`, `GET /api/automation/plan?lane_id=`, `POST /api/automation/runs` |
| Plans | `GET /api/automation/plans`, `PATCH /api/automation/plan`, `POST /api/admin/plans/sync-from-repo` |
| Lanes | `GET /api/dashboard/lanes`, `POST /api/admin/lanes`, `POST /api/admin/lanes/{id}/promote-to-live` |
| Dashboard | `GET /api/dashboard/stats`, `/runs`, `/decisions`, `/portfolio?lane_id=` |
| Admin | `POST /api/admin/robinhood-orders/import`, `/cursor-usage/import`, `/retention/run` |

Full table: [`api/README.md`](api/README.md). Interactive docs: `http://127.0.0.1:8000/docs`.

### Authentication

| Config | Effect |
|--------|--------|
| (default) | Dashboard GET endpoints are open on your network — use firewall/TLS in production |
| `MTA_READ_API_KEY` | Dashboard + automation read endpoints require `X-API-Key` |
| `MTA_DASHBOARD_PASSWORD` | Dashboard also accepts Bearer token from `POST /api/auth/login` |
| `MTA_WRITE_API_KEY` | Required on all POST/PATCH automation and admin writes |

## Modes and lanes

- Start in **research** mode (`trading_enabled: false`). Live `buy`/`sell` are blocked until mode is `live` and safety gates pass.
- **Multi-lane simulation**: each lane is a permanent paper track bound to one `plan_version` + `strategy_version`. Only one lane is **live** at a time.
- On OCI E2.1.Micro, set `MTA_SEQUENTIAL_LANES=true` so lanes run one at a time.

## GitHub Pages

1. Enable Pages on the `dashboard/` folder (or root with path).
2. Set `dashboard/config.js`: `API_BASE_URL`, optional `PLANS_REPO_URL`.
3. Add your Pages origin to `MTA_CORS_ORIGINS` on the API (e.g. `https://your-user.github.io`).

## Documentation index

| Doc | Topic |
|-----|--------|
| [dashboard/README.md](dashboard/README.md) | Dashboard UI, local dev, config |
| [docs/agent-plans.md](docs/agent-plans.md) | Plan JSON, GitHub edit workflow, sync |
| [docs/automation/research-prompt.md](docs/automation/research-prompt.md) | Cursor Automation standing instructions |
| [docs/automation/cursor-automation-setup.md](docs/automation/cursor-automation-setup.md) | Automation creation checklist |
| [docs/automation/multi-lane-simulation.md](docs/automation/multi-lane-simulation.md) | Lanes, live track, sequential mode |
| [docs/automation/multi-cadence.md](docs/automation/multi-cadence.md) | Multiple schedules / run types |
| [docs/safety-gates.md](docs/safety-gates.md) | Live trading gates |
| [docs/simulation-discipline.md](docs/simulation-discipline.md) | Paper portfolio rules |
| [docs/intervention-protocol.md](docs/intervention-protocol.md) | When the agent must stop |
| [docs/cost-tracking.md](docs/cost-tracking.md) | Cursor cost import |
| [docs/ops-oci.md](docs/ops-oci.md) | Production deployment |

## Status

Core API, multi-lane simulation, live money track, agent plan sync, and dashboard are implemented. See [`docs/PLAN.md`](docs/PLAN.md) for roadmap context.
