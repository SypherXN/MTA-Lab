# GitHub Pages dashboard deploy

Production dashboard config is **not** committed. The workflow [`.github/workflows/pages.yml`](workflows/pages.yml) generates `dashboard/config.js` at deploy time.

## Required setup

1. **Settings → Pages → Build and deployment → Source:** GitHub Actions
2. **Settings → Secrets and variables → Actions → Variables:**

| Variable | Example |
|----------|---------|
| `MTA_API_BASE_URL` | `https://mta-api.matthewgtran.com` |

## Recommended variables

| Variable | Example |
|----------|---------|
| `MTA_PLANS_REPO_URL` | `https://github.com/SypherXN/MTA-Lab` |
| `MTA_PLANS_REPO_BRANCH` | `main` |
| `MTA_PLANS_REPO_PATH` | `plans` |

## Optional secret (not recommended)

| Secret | Notes |
|--------|--------|
| `MTA_DASHBOARD_READ_KEY` | Injected into client JS — visible to visitors. Prefer API `MTA_DASHBOARD_PASSWORD` + dashboard login. |

## Deploy

- Push changes under `dashboard/`, **or**
- **Actions → Deploy GitHub Pages Dashboard → Run workflow** (e.g. after changing variables only)

Full details: [`dashboard/README.md`](../dashboard/README.md)
