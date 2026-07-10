#!/usr/bin/env bash
# Pull latest code, refresh deps/plans, restart MTA-Lab API.
set -euo pipefail

API_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_DIR="$(cd "${API_DIR}/.." && pwd)"
SERVICE_NAME="${MTA_SERVICE_NAME:-mta-lab-api}"

DO_PULL=1
DO_DEPS=1
DO_SYNC=1
DO_RESTART=1
DO_HEALTH=1
FORCE_PULL=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --no-pull         Skip git pull
  --no-deps         Skip pip install -r requirements.txt
  --no-sync-plans   Skip sync_plans_from_repo.py
  --no-restart      Skip systemctl restart
  --no-health       Skip post-update health check
  --force           Allow git pull with uncommitted VM changes
  -h, --help        Show this help

Safety: git pull is never run from cron. Refuses pull when the VM has
uncommitted changes unless --force is passed.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-pull) DO_PULL=0 ;;
    --no-deps) DO_DEPS=0 ;;
    --no-sync-plans) DO_SYNC=0 ;;
    --no-restart) DO_RESTART=0 ;;
    --no-health) DO_HEALTH=0 ;;
    --force) FORCE_PULL=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

cd "${REPO_DIR}"

if ((DO_PULL)); then
  if git rev-parse --is-inside-work-tree &>/dev/null; then
    dirty="$(git status --porcelain 2>/dev/null || true)"
    if [[ -n "${dirty}" && ${FORCE_PULL} -eq 0 ]]; then
      echo "Refusing git pull: uncommitted changes on VM." >&2
      echo "Review git status, then stash/commit or re-run with --force." >&2
      git status -sb >&2 || true
      exit 1
    fi
    ahead_behind="$(git rev-list --left-right --count "@{upstream}...HEAD" 2>/dev/null || echo "? ?")"
    echo "==> git fetch --dry-run (upstream: ${ahead_behind})"
    git fetch --dry-run 2>&1 || true
  fi
  echo "==> git pull --ff-only"
  git pull --ff-only
fi

cd "${API_DIR}"

if [[ ! -d .venv ]]; then
  echo "Missing .venv — run deploy/install.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ((DO_DEPS)); then
  echo "==> pip install -r requirements.txt"
  python -m pip install --upgrade pip
  pip install -r requirements.txt
fi

if ((DO_SYNC)); then
  echo "==> sync agent plans"
  python3 scripts/sync_plans_from_repo.py
fi

if ((DO_RESTART)); then
  if systemctl cat "${SERVICE_NAME}.service" &>/dev/null; then
    echo "==> systemctl restart ${SERVICE_NAME}"
    sudo systemctl restart "${SERVICE_NAME}.service"
  else
    echo "==> skip restart (systemd unit ${SERVICE_NAME} not installed)"
  fi
fi

if ((DO_HEALTH)); then
  echo "==> health check"
  sleep 2
  for _ in 1 2 3 4 5; do
    if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
      curl -fsS "http://127.0.0.1:8000/health"
      echo
      echo "Update complete."
      exit 0
    fi
    sleep 2
  done
  echo "Health check failed after update." >&2
  journalctl -u "${SERVICE_NAME}.service" -n 30 --no-pager 2>/dev/null || true
  exit 1
fi

echo "Update steps finished."
