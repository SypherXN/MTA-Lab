#!/usr/bin/env bash
set -uo pipefail
cd /home/mattg/repos/MTA-Lab
RESULT_FILE="/home/mattg/repos/MTA-Lab/push-result.txt"

{
  echo "=== STEP 1: Shell verification ==="
  echo test
  echo ""
  echo "=== STEP 2: Working directory ==="
  pwd
  echo ""
  echo "=== STEP 3: git status ==="
  git status
  echo ""
  echo "=== STEP 3: git remote -v ==="
  git remote -v
  echo ""
  echo "=== STEP 3: ls -la .git/objects | head ==="
  ls -la .git/objects | head
  echo ""
  echo "=== STEP 4: gh auth status ==="
  gh auth status 2>&1
  echo ""
  echo "=== STEP 5: git add -A ==="
  git add -A
  STAGED=$(git diff --cached --name-only | wc -l)
  echo "Staged file count: $STAGED"
  git diff --cached --name-only
  echo ""
  echo "=== STEP 5b: git user identity (local) ==="
  GH_USER=$(gh api user --jq .login)
  GH_EMAIL=$(gh api user --jq .email)
  if [ -z "$GH_EMAIL" ] || [ "$GH_EMAIL" = "null" ]; then
    GH_EMAIL="${GH_USER}@users.noreply.github.com"
  fi
  git config user.name "$GH_USER"
  git config user.email "$GH_EMAIL"
  echo "user.name=$GH_USER"
  echo "user.email=$GH_EMAIL"
  echo ""
  echo "=== STEP 6: Initial commit ==="
  if [ "$STAGED" -gt 0 ] && ! git rev-parse --verify HEAD >/dev/null 2>&1; then
    git commit -m "Initial commit: MTA-Lab API, dashboard, automation docs, and agent skills."
    echo "Commit exit code: $?"
    git log -1 --oneline
  else
    echo "Skipped commit"
  fi
  echo ""
  echo "=== STEP 7: git push -u origin main ==="
  git push -u origin main 2>&1
  echo "Push exit code: $?"
  echo ""
  echo "=== FINAL: git status ==="
  git status
  echo ""
  echo "=== FINAL: git log -1 ==="
  git log -1 --oneline 2>&1 || echo "No commits"
} > "$RESULT_FILE" 2>&1

cat "$RESULT_FILE"
