#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== gitignore check ==="
git check-ignore -v .local/feature-roadmap.md || true

echo "=== staging ==="
git add -A
if git diff --cached --name-only | grep -qE '^\.local/|\.env$|\.venv/|\.db$'; then
  echo "ERROR: forbidden paths staged" >&2
  git diff --cached --name-only
  exit 1
fi

echo "=== staged files ($(git diff --cached --name-only | wc -l)) ==="
git diff --cached --name-only | head -40

if git rev-parse HEAD >/dev/null 2>&1; then
  if git diff --cached --quiet; then
    echo "=== nothing to commit ==="
  else
    git commit -m "$(cat <<'EOF'
Update MTA-Lab: API, dashboard, docs, and agent skills.

Includes plan versioning, decision scoring, implement-by-id skill, and local roadmap gitignore.
EOF
)"
  fi
else
  git commit -m "$(cat <<'EOF'
Initial commit: MTA-Lab API, dashboard, automation docs, and agent skills.

FastAPI/SQLite backend with research-mode safety, plan versioning, decision scoring, dashboard, GitHub Pages workflow, and implement-by-id project skill.
EOF
)"
fi

echo "=== pushing ==="
git push -u origin main

echo "=== done ==="
git status -sb
git log -1 --oneline
