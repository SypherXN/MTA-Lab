# MTA-Lab roadmap lookup

## Primary source

Feature IDs live in the local roadmap (not in git):

- `.local/feature-roadmap.md`

Fallback: `~/.cursor/plans/mta_feature_roadmap*.plan.md` if the local copy is missing.

Grep for the ID (e.g. `AP-03`, `DA-01`) to get description, benefit, impact, difficulty, and completion status.

## ID prefixes

| Prefix | Area |
|--------|------|
| `AP-*` | Cursor Automation / agent plan behavior |
| `CA-*` | Cursor Automation infrastructure |
| `DA-*` | Dashboard |
| `DB-*` | SQLite schema / data model |
| `API-*` | FastAPI endpoints and services |

## Common touchpoints

| Area | Typical paths |
|------|----------------|
| API | `api/app/`, `api/schema.sql`, `api/tests/test_api.py`, `api/README.md` |
| Dashboard | `dashboard/` |
| Automation docs | `docs/automation/` |
| Ops | `docs/ops-oci.md`, `api/deploy/` |

## Completion marker

When done, update the plan section heading to include `✅ Completed` and add an **Implementation** bullet block (see AP-01/AP-02 in the plan for examples).

## Tests

From WSL:

```bash
cd ~/repos/MTA-Lab/api && source .venv/bin/activate && MTA_RATE_LIMIT_ENABLED=false python -m unittest discover -s tests -p 'test_*.py' -v
```

Set `MTA_RATE_LIMIT_ENABLED=false` in tests. Use a fresh test DB if plan-mutating tests affect ordering (`rm -f /tmp/mta_lab_test.db`).
