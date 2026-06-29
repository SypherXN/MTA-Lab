# MTA-Lab

Market Test Agent Lab — an auditable agentic trading system for research-first market testing.

Scheduled **Cursor Automations** use **Robinhood MCP** for quotes, portfolio data, and order review. Strategy, context, run logs, and simulated portfolio state live in a small **OCI-hosted API**. A **GitHub Pages** dashboard reads from that API.

## Architecture

```
Cursor Automation (schedule)
  → GET  /api/automation/context
  → Robinhood MCP (read + review_equity_order)
  → POST /api/automation/runs
GitHub Pages dashboard → GET /api/dashboard/*
```

## Quick start (API)

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
python -m unittest discover -s tests -p 'test_*.py'
```

## Quick start (dashboard)

```bash
cd dashboard
cp config.example.js config.js
# edit API_BASE_URL if needed
python3 -m http.server 8080
```

Open `http://localhost:8080` with the API running on port 8000.

## Repo layout

| Path | Purpose |
|------|---------|
| [`api/`](api/) | FastAPI service + SQLite |
| [`dashboard/`](dashboard/) | Static GitHub Pages frontend |
| [`docs/automation/`](docs/automation/) | Cursor Automation prompt and setup |
| [`docs/safety-gates.md`](docs/safety-gates.md) | Live trading safety rules |
| [`docs/cost-tracking.md`](docs/cost-tracking.md) | Cursor usage reconciliation |
| [`docs/ops-oci.md`](docs/ops-oci.md) | OCI deployment notes |

## API endpoints

| Method | Path | Auth |
|--------|------|------|
| GET | `/health` | none |
| GET | `/api/automation/context` | none |
| POST | `/api/automation/runs` | `X-API-Key` |
| GET | `/api/dashboard/runs` | none |
| GET | `/api/dashboard/decisions` | none |
| GET | `/api/dashboard/stats` | none |
| GET | `/api/dashboard/portfolio` | none |
| GET | `/api/dashboard/usage` | none |
| PATCH | `/api/automation/strategy` | `X-API-Key` |
| POST | `/api/automation/notes` | `X-API-Key` |
| POST | `/api/admin/cursor-usage/import` | `X-API-Key` |

## Modes

Start in **research** mode (`trading_enabled: false`). The agent may read markets and call `review_equity_order`, but the API blocks live `buy` / `sell` decisions until strategy mode is `live`.

## GitHub Pages

Publish the `dashboard/` folder via GitHub Pages. Set `dashboard/config.js` to your deployed API URL and add that origin to `MTA_CORS_ORIGINS` on the API.

## Status

Implementation scaffold for the Market Test Agent Lab plan. See [`docs/PLAN.md`](docs/PLAN.md) for the full design reference.
