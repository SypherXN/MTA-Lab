# Agent Plans

Agent plans define **how** the automation operates: run order, required inputs, scoring rules, data sources, and stop conditions. They do **not** set trading caps (those live in **strategy** rules).

## Source of truth: GitHub repo

Plan content is stored as JSON files in [`plans/`](../plans/) at the repo root:

```text
plans/
  v1.json          # default research plan
  v2.json          # e.g. technical archetype (when added)
  v3.json          # e.g. sentiment archetype (when added)
```

**Edit flow:**

1. Change `plans/<version>.json` in GitHub (or locally and push).
2. On the API host, `git pull` then sync into SQLite:

```bash
cd ~/MTA-Lab
python3 api/scripts/sync_plans_from_repo.py
```

Or via API:

```bash
curl -X POST "$API/api/admin/plans/sync-from-repo" \
  -H "X-API-Key: $WRITE_KEY"
```

3. Lanes pinned to that `plan_version` immediately use the updated content (same version string, new content hash).

The dashboard **Agent Plans** section is read-only. For **Edit on GitHub** links, set the `MTA_PLANS_REPO_URL` repository variable (GitHub Actions deploy) or `PLANS_REPO_URL` in local `dashboard/config.js` — see [dashboard/README.md](../dashboard/README.md).

## File format

Each file is a JSON object with metadata plus plan sections (or a nested `plan` object):

```json
{
  "version": "v1",
  "name": "Default Research Agent Plan",
  "change_source": "github",
  "is_active": false,
  "run_order": [ ... ],
  "required_inputs": [ ... ],
  "scoring_rules": [ ... ],
  "data_sources": [ ... ],
  "stop_conditions": [ ... ]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `version` | yes | Must match filename stem (`v1.json` → `"v1"`) |
| `name` | yes | Human label |
| `change_source` | no | Stored on sync (default `github`) |
| `is_active` | no | If `true`, marks this version as the global active plan on insert |
| `plan` | no | Alternative wrapper; inner object used if present |

Sections match `AgentPlanPayload` in the API (`api/app/schemas.py`). See seeded content in [`api/app/plan_defaults.py`](../api/app/plan_defaults.py) and [`plans/v1.json`](../plans/v1.json).

## Versioning and lanes

| Mechanism | Behavior |
|-----------|----------|
| **Sync in place** | Editing `v1.json` updates plan `v1` in the DB; lanes bound to `v1` pick up changes |
| **New version file** | Add `v2.json`, sync, create or update a lane with `plan_version: "v2"` |
| **`PATCH /api/automation/plan`** | Creates a **new** active version (v2, v3, …) from the current active plan — use for API-only edits; prefer repo sync for operator workflow |

Each **simulation lane** is pinned to one `plan_version` at creation. Automations load the lane's plan via:

```http
GET /api/automation/plan?lane_id=2
```

## API endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/automation/plan` | Read* | Active plan, or lane's plan when `?lane_id=` |
| GET | `/api/automation/plans` | Read* | Version history summaries |
| GET | `/api/automation/plans/{version}` | Read* | Full plan snapshot |
| PATCH | `/api/automation/plan` | Write | Bump active plan version (API workflow) |
| POST | `/api/admin/plans/sync-from-repo` | Write | Import all `plans/*.json` |

\*Read auth when `MTA_READ_API_KEY` is set.

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `MTA_PLANS_REPO_DIR` | `../plans` from `api/` | Override plans directory for sync |

Resolved path: repo root `plans/` unless overridden.

## Multi-lane setup

1. Add one JSON file per plan approach (`v1.json`, `v2.json`, …).
2. Sync: `python3 api/scripts/sync_plans_from_repo.py`
3. Create lanes with distinct `plan_version` values — see [multi-lane-simulation.md](automation/multi-lane-simulation.md).
4. View and compare in the dashboard **Agent Plans** and **Lane Comparison** sections.

## Related docs

- [Research prompt](automation/research-prompt.md) — how automations consume the plan
- [Multi-lane simulation](automation/multi-lane-simulation.md)
- [Dashboard README](../dashboard/README.md)
