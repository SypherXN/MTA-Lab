---
name: implement-by-id
description: >-
  Resolves an issue or feature by ID from project documentation or plans,
  implements or fixes the work, runs tests, and updates docs to reflect current
  status. Use when the user invokes /implement-by-id, references an
  issue/feature ID (AP-01, DA-03, DB-02), or asks to implement, fix, or
  complete a tracked item by ID.
disable-model-invocation: true
---

# Implement by ID

End-to-end workflow: **resolve ID → implement/fix → test → update docs**.

The user supplies an **ID** (any format: `AP-02`, `#42`, `phase-2`, `dashboard-stats`, etc.). Treat that ID as the anchor for the whole run.

For MTA-Lab roadmap IDs (`AP-*`, `DA-*`, `DB-*`, `CA-*`, `API-*`), see [mta-lab-roadmap.md](mta-lab-roadmap.md).

## Workflow checklist

Copy and track progress:

```
Implement by ID: [ID]
- [ ] Step 1: Resolve ID in docs/plan
- [ ] Step 2: Implement or fix
- [ ] Step 3: Run tests and verify
- [ ] Step 4: Update documentation/plan
```

Do not mark the task complete until all four steps pass.

---

## Step 1: Identify using ID from documentation or plan

Search until the ID resolves to a concrete work item with scope and acceptance criteria.

**Search order** (stop when found; otherwise continue):

1. **Local roadmap** — `.local/feature-roadmap.md`
2. **Cursor plans** — `~/.cursor/plans/*.plan.md` (fallback)
3. **Project docs** — `docs/`, `README.md`, `docs/PLAN.md`, `AGENTS.md`
4. **GitHub** — `gh issue view <n>` or `gh pr view <n>` when the ID looks like an issue/PR number
5. **Codebase** — grep for the ID string in comments, TODOs, test names, or config

**Extract and restate before coding:**

- Title and type (bug, feature, chore, doc)
- Current status (todo, in progress, blocked, done)
- Acceptance criteria or expected behavior
- Files/modules likely involved
- Related tests (if named in the doc)

**If the ID is ambiguous or not found:** report what was searched, list closest matches, and ask the user to clarify. Do not guess scope.

---

## Step 2: Fix or implement

Follow project conventions. Keep the diff focused on the resolved work item only.

1. Read surrounding code before editing; match existing patterns.
2. Implement the smallest change that satisfies acceptance criteria.
3. Handle edge cases called out in the doc; do not expand scope.
4. If the item is already done, verify against criteria and skip to Step 3.

**Blockers:** If implementation requires a product/architecture decision not covered by the doc, stop and ask rather than inventing behavior.

---

## Step 3: Run test cases to verify it works properly

Run the project's test suite, prioritizing tests tied to the changed area.

**MTA-Lab canonical test command** (WSL):

```bash
cd ~/repos/MTA-Lab/api && source .venv/bin/activate && MTA_RATE_LIMIT_ENABLED=false python -m unittest discover -s tests -p 'test_*.py' -v
```

**Rules:**

- Run tests yourself; do not ask the user to verify.
- If tests fail, fix and re-run until passing or you hit a genuine blocker.
- Add or extend tests when the change lacks coverage for new behavior.
- For UI or integration work with no automated test, document manual verification steps in the completion report.

---

## Step 4: Update documentation and/or plan to match current status

Sync tracking docs with what was actually built. Update every location where the ID appears.

**Typical updates:**

- Mark item **done** (`✅ Completed` in the Cursor plan, checkbox, or status field)
- Add a short **Implementation** note with endpoints, tables, config, or files touched
- Update `api/README.md` or `docs/` when behavior or env vars change
- If partially done, set status to **in progress** and list remaining work

**Do not** edit unrelated docs. Match the doc's existing tone and structure.

---

## Completion report

End every run with:

```markdown
## [ID] — [Title]

**Status:** Done | Partial | Blocked

**Changes:**
- [file/path] — brief description

**Tests:** [command run] — pass/fail count

**Docs updated:**
- [path] — what changed

**Notes:** (optional — blockers, follow-ups, manual verification)
```

Only commit or open a PR when the user explicitly asks.
