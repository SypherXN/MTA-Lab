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

**Local dev:** copy from `config.example.js` and edit (file is gitignored).

**GitHub Pages:** `config.js` is **generated at deploy time** by `.github/workflows/pages.yml` from repository variables/secrets — never commit production values.

### GitHub repository settings

Repo → **Settings** → **Secrets and variables** → **Actions**:

| Name | Type | Required | Example |
|------|------|----------|---------|
| `MTA_API_BASE_URL` | Variable | Yes | `https://mta-api.matthewgtran.com` |
| `MTA_PLANS_REPO_URL` | Variable | No | `https://github.com/SypherXN/MTA-Lab` |
| `MTA_PLANS_REPO_BRANCH` | Variable | No | `main` |
| `MTA_PLANS_REPO_PATH` | Variable | No | `plans` |
| `MTA_DASHBOARD_READ_KEY` | Secret | No | same as API `MTA_READ_API_KEY` |

Also enable Pages: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

Quick reference: [`.github/DASHBOARD_DEPLOY.md`](../.github/DASHBOARD_DEPLOY.md).

Regenerate locally (optional):

```bash
MTA_API_BASE_URL=http://localhost:8000 ./dashboard/scripts/generate-config.sh
```

| Key in `config.js` | Purpose |
|-----|---------|
| `API_BASE_URL` | API origin (required) |
| `API_READ_KEY` | Optional; only set via secret if you accept it is visible in the browser |
| `PLANS_REPO_URL` | GitHub repo base URL for "Edit on GitHub" links |
| `PLANS_REPO_BRANCH` | Branch name (default `main`) |
| `PLANS_REPO_PATH` | Path to plan folder (default `plans`) |

### Security notes

- Repository **secrets/variables** keep values out of git — good.
- Anything injected into `config.js` is still **public to visitors** (view source / `config.js`). `API_BASE_URL` and plan repo URLs are fine.
- **`API_READ_KEY` in client JS is extractable.** Prefer **dashboard password login** (`MTA_DASHBOARD_PASSWORD` on API only) and leave `MTA_DASHBOARD_READ_KEY` unset in GitHub.
- **Never** put `MTA_WRITE_API_KEY` in dashboard config or GitHub variables for Pages.

### Authentication

1. **No password, no read key** (typical local dev) — dashboard loads without login.
2. **`MTA_READ_API_KEY` on API** — either:
   - **Production (recommended):** leave `MTA_DASHBOARD_READ_KEY` unset in GitHub; set `MTA_DASHBOARD_PASSWORD` on the API and sign in on the dashboard.
   - **Optional:** set `MTA_DASHBOARD_READ_KEY` repository secret (injected into generated `config.js` — still visible to visitors).
   - **Local dev:** set `API_READ_KEY` in gitignored `config.js`, or use login if password is set.
3. **`MTA_DASHBOARD_PASSWORD` on API** — sign in on the login screen; token stored in `localStorage`.

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

1. **Settings → Pages → Source:** **GitHub Actions** (workflow `.github/workflows/pages.yml`).
2. **Settings → Secrets and variables → Actions** — set variables (and optional secret) per table in [Configuration](#configuration-configjs) above.
3. Push changes under `dashboard/`, **or** run **Actions → Deploy GitHub Pages Dashboard** after changing repository variables only.
4. Add your Pages URL to `MTA_CORS_ORIGINS` on the API.

Do **not** commit `dashboard/config.js` for production (gitignored; CI generates it).

## Related docs

- [Agent plans](../docs/agent-plans.md) — editing plan JSON in GitHub
- [Multi-lane simulation](../docs/automation/multi-lane-simulation.md) — lane model
- [API README](../api/README.md) — endpoint reference
