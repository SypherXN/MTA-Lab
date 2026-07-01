# MTA-Lab Dashboard

Static frontend for run history, lane comparison, portfolio views, safety controls, and agent plan inspection. Deployed via **GitHub Pages** or served locally for development.

## Local development

```bash
# Terminal 1 — API
cd api && ./run.sh

# Terminal 2 — dashboard
cd dashboard
cp config.example.js config.js
python3 -m http.server 8080
```

Open **http://localhost:8080**.

Ensure `api/.env` includes:

```bash
MTA_CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
MTA_DASHBOARD_PASSWORD=          # empty for local dev (no login)
MTA_SEQUENTIAL_LANES=false       # local dev; true on OCI micro
```

Hard refresh after pulling UI changes (`Ctrl+Shift+R`).

## Configuration (`config.js`)

Copy from `config.example.js`:

| Key | Purpose |
|-----|---------|
| `API_BASE_URL` | API origin (required), e.g. `https://api.example.com` |
| `API_READ_KEY` | Optional; sent as `X-API-Key` when `MTA_READ_API_KEY` is set on API |
| `PLANS_REPO_URL` | GitHub repo base URL for "Edit on GitHub" links in Agent Plans |
| `PLANS_REPO_BRANCH` | Branch name (default `main`) |
| `PLANS_REPO_PATH` | Path to plan folder (default `plans`) |

### Authentication

1. **No password, no read key** (typical local dev) — dashboard loads without login.
2. **`MTA_READ_API_KEY` set** — set `API_READ_KEY` in `config.js`, or use dashboard login if password is also set.
3. **`MTA_DASHBOARD_PASSWORD` set** — sign in on the login screen; token stored in `localStorage`.

`GET /api/auth/status` reports whether login is required.

## UI sections

| Section | Description |
|---------|-------------|
| **Stats grid** | Run counts, trades, Cursor cost |
| **Live Money Track** | Stitched real-money equity across live stints; handoff timeline |
| **Simulation Lanes** | Lane cards (live / shadow / research) with portfolio and plan links |
| **Agent Plans** | Read-only plan viewer per lane (expand to load); GitHub edit link when configured |
| **Lane Comparison** | Head-to-head metrics per lane |
| **Strategy** | Active strategy summary and intervention status |
| **Safety Controls** | Edit mode, kill switch, caps (`PATCH /api/dashboard/strategy`) |
| **Simulated Portfolio** | Per-lane cash, positions, P&L (lane selector) |
| **Portfolio Snapshots** | Equity snapshot summary for selected lane |
| **Reconciliation / Freshness** | Order linkage and data staleness |
| **Alert Inbox** | Open alerts with acknowledge/resolve |
| **Paper Portfolio Comparison** | Multi-lane equity overlay chart |
| **Timeline / Cost / Runs / Decisions** | Activity and audit views |

## Styling

The dashboard uses a **pastel green** theme (mint background, sage cards, forest green accents). Styles live in `styles.css`; cache-busting query params on CSS/JS in `index.html` help during local iteration.

## GitHub Pages deployment

1. Publish the `dashboard/` directory (or configure Pages path).
2. Create `config.js` on the branch Pages serves (do not commit secrets — use a public read key only if needed).
3. Set `API_BASE_URL` to your HTTPS API.
4. Add the Pages URL to `MTA_CORS_ORIGINS` on the API.

## Related docs

- [Agent plans](../docs/agent-plans.md) — editing plan JSON in GitHub
- [Multi-lane simulation](../docs/automation/multi-lane-simulation.md) — lane model
- [API README](../api/README.md) — endpoint reference
