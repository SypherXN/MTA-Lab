---
name: Ponytail Cleanup
overview: Cut over-engineering found by the ponytail audit — dead scripts/routes, unused YAGNI features, duplicate layers, and plan/schema duplication. Companion doc .local/ponytail-cleanup.md.
todos:
  - id: dead-scripts
    num: 1
    content: Delete unused shell scripts (push-to-github, run-push-diagnose, api/run.sh)
    status: completed
  - id: config-dead-fields
    num: 2
    content: Remove Settings fields never read by Python (backup_keep, watcher_pct_threshold)
    status: completed
  - id: micro-wrappers
    num: 3
    content: Inline one-line wrappers and duplicate constants
    status: completed
  - id: drop-multipart
    num: 4
    content: Remove unused python-multipart dependency
    status: completed
  - id: dead-dashboard-routes
    num: 5
    content: Remove dashboard routes with no UI callers
    status: completed
  - id: drop-backtest
    num: 6
    content: Remove unused decision backtest replay feature
    status: completed
  - id: drop-rollups
    num: 7
    content: Remove unused daily rollups feature (no cron, no dashboard)
    status: completed
  - id: drop-compact-payload
    num: 8
    content: Remove write-only compact payload path
    status: completed
  - id: freshness-dedupe
    num: 9
    content: Collapse duplicate freshness endpoints to one
    status: completed
  - id: portfolio-route-dedupe
    num: 10
    content: Collapse duplicate portfolio-snapshot routes
    status: completed
  - id: dashboard-ui-shrink
    num: 11
    content: Merge apiHeaders helpers and duplicate CSS
    status: completed
  - id: plan-defaults-load
    num: 12
    content: Delete plan_defaults.py; seed from plans/v1.json
    status: completed
  - id: plan-base-extract
    num: 13
    content: Extract shared plan boilerplate into base + deltas
    status: completed
  - id: migration-inline
    num: 14
    content: Inline migration_service.py into database.py
    status: completed
  - id: schema-unify
    num: 15
    content: Unify schema.sql + migrations + ALTER path into one mechanism
    status: completed
  - id: drop-httpx
    num: 16
    content: "(Deferred) Replace httpx with urllib in three call sites"
    status: cancelled
isProject: true
---

# Ponytail Cleanup

Cut complexity from the [ponytail audit](../ponytail-cleanup.md) — dead code, unused flexibility, duplicate layers. Correctness/security/perf out of scope.

**Reference doc:** [`.local/ponytail-cleanup.md`](../../.local/ponytail-cleanup.md)

## Goals

- Remove write-only / never-wired features and dead scripts
- Collapse duplicate API routes and thin wrappers
- Deduplicate plan and schema boilerplate without changing runtime behavior

## Task index

| # | id | status | summary |
|---|-----|--------|---------|
| 1 | `dead-scripts` | completed | Delete unused shell scripts |
| 2 | `config-dead-fields` | completed | Drop unread Settings fields |
| 3 | `micro-wrappers` | completed | Inline one-line wrappers / dup constants |
| 4 | `drop-multipart` | completed | Remove python-multipart |
| 5 | `dead-dashboard-routes` | completed | Remove unused dashboard routes |
| 6 | `drop-backtest` | completed | Remove backtest replay feature |
| 7 | `drop-rollups` | completed | Remove daily rollups feature |
| 8 | `drop-compact-payload` | completed | Remove compact payload path |
| 9 | `freshness-dedupe` | completed | One freshness endpoint surface |
| 10 | `portfolio-route-dedupe` | completed | One portfolio-snapshot namespace |
| 11 | `dashboard-ui-shrink` | completed | Merge apiHeaders + CSS dupes |
| 12 | `plan-defaults-load` | completed | Seed plan from v1.json |
| 13 | `plan-base-extract` | completed | Shared plan base + deltas |
| 14 | `migration-inline` | completed | Inline migration_service |
| 15 | `schema-unify` | completed | Single schema/migration mechanism |
| 16 | `drop-httpx` | cancelled | (Deferred) urllib instead of httpx |

## Task details

### [#1] [dead-scripts] Delete unused shell scripts

**Num:** 1
**Status:** completed
**Priority:** high

**Scope:** Remove one-off / duplicate launchers not referenced by ops docs or `mta` tooling. Do not remove `scripts/mta` or `api/scripts/mta-ctl.sh`.

**Acceptance criteria:**
- [x] `scripts/run-push-diagnose.sh` deleted
- [x] `scripts/push-to-github.sh` deleted
- [x] `api/run.sh` deleted (keep `api/scripts/run.sh`)
- [x] No remaining references in README / deploy docs (or docs updated)

**Files:**
- `scripts/run-push-diagnose.sh` — delete
- `scripts/push-to-github.sh` — delete
- `api/run.sh` — delete

**Depends on:** none

---

### [#2] [config-dead-fields] Remove unread Settings fields

**Num:** 2
**Status:** completed
**Priority:** medium

**Scope:** Drop Python `Settings` fields that nothing in `api/app/` reads. Shell scripts that read env vars directly keep working.

**Acceptance criteria:**
- [x] `backup_keep` removed from `Settings` (and `.env.example` if present)
- [x] `watcher_pct_threshold` removed from `Settings` (and `.env.example` if present)
- [x] App still starts; scripts still use env vars as before

**Files:**
- `api/app/config.py`
- `api/.env.example` (if fields listed)

**Depends on:** none

---

### [#3] [micro-wrappers] Inline thin wrappers and duplicate constants

**Num:** 3
**Status:** completed
**Priority:** medium

**Scope:** Small inlines only — no behavior change.

**Acceptance criteria:**
- [x] `sequential_lanes_enabled()` removed; callers use `settings.sequential_lanes`
- [x] `count_table_rows` alias removed or collapsed to one name
- [x] Duplicate `mta-ctl.sh` production-harden aliases reduced to one
- [x] `DECISION_SELECT_COLUMNS` / `DECISION_SELECT_ALIASED` collapsed if safe
- [x] Tests still pass

**Files:**
- `api/app/lane_execution_service.py`
- `api/app/db_monitor_service.py`
- `api/scripts/mta-ctl.sh`
- `api/app/decision_utils.py`

**Depends on:** none

---

### [#4] [drop-multipart] Remove unused python-multipart

**Num:** 4
**Status:** completed
**Priority:** high

**Scope:** Dependency has no `UploadFile`/`Form` usage.

**Acceptance criteria:**
- [x] `python-multipart` removed from `requirements.txt`
- [x] App and tests still import/start cleanly

**Files:**
- `api/requirements.txt`

**Depends on:** none

---

### [#5] [dead-dashboard-routes] Remove unused dashboard routes

**Num:** 5
**Status:** completed
**Priority:** high

**Scope:** Delete dashboard router endpoints with no `dashboard/app.js` callers. Keep automation equivalents where they exist and are used.

**Acceptance criteria:**
- [x] Unused routes removed: `/news`, `/preflight`, `/usage/budget`, `/strategy/performance`, `/db/snapshots`, `/rollups`, `/backtest/replay`, `/export/json` (confirm each against `app.js` before delete)
- [x] `api/README.md` trimmed to match remaining endpoints
- [x] Dashboard still loads; tests updated

**Files:**
- `api/app/routers/dashboard.py`
- `api/README.md`
- `api/tests/test_api.py` (if route tests exist)

**Depends on:** none — coordinate with #6/#7 if those routes are removed there first

---

### [#6] [drop-backtest] Remove backtest replay feature

**Num:** 6
**Status:** completed
**Priority:** high

**Scope:** Full removal of decision replay — service, schemas, routes, tests, docs mentions.

**Acceptance criteria:**
- [x] `backtest_service.py` deleted
- [x] Dashboard/admin routes and schemas for replay removed
- [x] Tests and README references removed
- [x] No import errors

**Files:**
- `api/app/backtest_service.py` — delete
- `api/app/routers/dashboard.py`
- `api/app/schemas.py`
- `api/tests/test_api.py`
- `api/README.md`

**Depends on:** none (can land with #5)

---

### [#7] [drop-rollups] Remove daily rollups feature

**Num:** 7
**Status:** completed
**Priority:** high

**Scope:** No cron wiring and no dashboard fetch — remove rather than wire (ponytail preference). Leave DB table if already migrated (orphan table OK) unless cheap to drop via migration.

**Acceptance criteria:**
- [x] `rollup_service.py` deleted
- [x] Admin `rollups/run` and dashboard list routes removed
- [x] Related schemas/tests/docs removed
- [x] API tests pass

**Files:**
- `api/app/rollup_service.py` — delete
- `api/app/routers/admin.py`
- `api/app/routers/dashboard.py`
- `api/app/schemas.py`
- `api/tests/test_api.py`

**Depends on:** none (can land with #5)

---

### [#8] [drop-compact-payload] Remove write-only compact payload

**Num:** 8
**Status:** completed
**Priority:** high

**Scope:** Admin write path with unread `get_compact_payload`. Remove service + route. Keep existing DB rows/table unless a clean migration is trivial.

**Acceptance criteria:**
- [x] `payload_service.py` deleted (or reduced to nothing and deleted)
- [x] Admin compact-payload route removed
- [x] Tests/docs cleaned
- [x] No callers remain

**Files:**
- `api/app/payload_service.py` — delete
- `api/app/routers/admin.py`
- `api/app/schemas.py`
- `api/tests/test_api.py`

**Depends on:** none

---

### [#9] [freshness-dedupe] Collapse freshness endpoints

**Num:** 9
**Status:** completed
**Priority:** medium

**Scope:** `get_data_freshness()` is a thin alias; four routes expose overlapping data. Keep one check endpoint per consumer surface (prefer `/freshness/check`).

**Acceptance criteria:**
- [x] Redundant `/freshness` (non-check) routes removed from automation and/or dashboard
- [x] Thin alias inlined or removed
- [x] Dashboard/automation callers updated if any
- [x] Tests updated

**Files:**
- `api/app/freshness_service.py`
- `api/app/routers/automation.py`
- `api/app/routers/dashboard.py`

**Depends on:** #5 preferred first

---

### [#10] [portfolio-route-dedupe] Collapse portfolio-snapshot routes

**Num:** 10
**Status:** completed
**Priority:** medium

**Scope:** Same `dashboard_service` delegates on automation + dashboard. Pick one public namespace; update callers.

**Acceptance criteria:**
- [x] Duplicate snapshot list/summary routes removed from one router
- [x] Remaining callers (dashboard JS, tests, prompts) point at surviving paths
- [x] Tests pass

**Files:**
- `api/app/routers/automation.py`
- `api/app/routers/dashboard.py`
- `dashboard/app.js` (if needed)

**Depends on:** #5 preferred first

---

### [#11] [dashboard-ui-shrink] Merge apiHeaders and CSS dupes

**Num:** 11
**Status:** completed
**Priority:** low

**Scope:** Frontend-only shrink; no API change.

**Acceptance criteria:**
- [x] Single `apiHeaders` helper covers JSON vs read-only cases
- [x] Duplicate `.legacy-compare summary` CSS blocks merged
- [x] Dashboard still works visually

**Files:**
- `dashboard/app.js`
- `dashboard/styles.css`

**Depends on:** none

---

### [#12] [plan-defaults-load] Seed plan from v1.json

**Num:** 12
**Status:** completed
**Priority:** high

**Scope:** Delete near-duplicate `plan_defaults.py`; `_seed_agent_plan_if_empty` loads `plans/v1.json` via `settings.resolved_plans_dir()`.

**Acceptance criteria:**
- [x] `api/app/plan_defaults.py` deleted
- [x] Fresh DB seed creates plan v1 from `plans/v1.json`
- [x] Tests covering seed/init still pass

**Files:**
- `api/app/plan_defaults.py` — delete
- `api/app/database.py`
- `api/tests/test_api.py`

**Depends on:** none

---

### [#13] [plan-base-extract] Extract shared plan boilerplate

**Num:** 13
**Status:** completed
**Priority:** medium

**Scope:** `v1`–`v3` share most `run_order` / inputs / stop conditions. Introduce a base + per-version overlays without changing synced plan content hashes unexpectedly — or accept re-sync on deploy.

**Acceptance criteria:**
- [x] Shared sections live in one base file (or sync-time merge)
- [x] `v1`–`v4` still sync via `sync_plans_from_repo`
- [x] Lane-bound plan versions still load correct behavior
- [x] Net line count in `plans/` drops materially

**Files:**
- `plans/`
- `api/app/plan_service.py` (if merge logic needed)
- `api/scripts/sync_plans_from_repo.py`

**Depends on:** #12 recommended first

---

### [#14] [migration-inline] Inline migration_service

**Num:** 14
**Status:** completed
**Priority:** medium

**Scope:** 29-line wrapper only called from `database._migrate_schema`. Inline `apply_pending_migrations`.

**Acceptance criteria:**
- [x] `migration_service.py` deleted
- [x] Migrations still apply on init
- [x] Tests pass

**Files:**
- `api/app/migration_service.py` — delete
- `api/app/database.py`

**Depends on:** none — do before #15

---

### [#15] [schema-unify] Unify schema migration mechanism

**Num:** 15
**Status:** completed
**Priority:** low

**Scope:** Today: full `schema.sql` + `migrations.py` + ALTER blocks in `database.py`. Choose one primary path (prefer numbered `MIGRATIONS` + minimal bootstrap schema). Highest risk cleanup — verify on fresh and existing DBs.

**Acceptance criteria:**
- [x] Single documented migration path
- [x] Fresh init creates full schema
- [x] Existing DB upgrades without data loss
- [x] Init/migration tests pass

**Files:**
- `api/schema.sql`
- `api/app/migrations.py`
- `api/app/database.py`

**Depends on:** #14

---

### [#16] [drop-httpx] Replace httpx with urllib

**Num:** 16
**Status:** cancelled

**Scope:** (Deferred) Three sync call sites only — optional dep cut, higher churn than value for now.

**Acceptance criteria:**
- [ ] N/A while cancelled

**Files:**
- `api/requirements.txt`
- `api/app/alert_service.py`
- `api/scripts/price_watcher.py`
- `api/scripts/seed_sample_run.py`

**Depends on:** none

## Implementation order

✅ 1. #1 `dead-scripts`
✅ 2. #2 `config-dead-fields`
✅ 3. #3 `micro-wrappers`
✅ 4. #4 `drop-multipart`
✅ 5. #6 `drop-backtest`
✅ 6. #7 `drop-rollups`
✅ 7. #8 `drop-compact-payload`
✅ 8. #5 `dead-dashboard-routes`
✅ 9. #9 `freshness-dedupe`
✅ 10. #10 `portfolio-route-dedupe`
✅ 11. #11 `dashboard-ui-shrink`
✅ 12. #12 `plan-defaults-load`
✅ 13. #13 `plan-base-extract`
✅ 14. #14 `migration-inline`
✅ 15. #15 `schema-unify`
16. ~~#16 `drop-httpx`~~ cancelled (deferred)