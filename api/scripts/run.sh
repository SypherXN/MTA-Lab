#!/usr/bin/env bash
# Dev server (not for production — use systemd install-service.sh on VM).
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -d .venv ]]; then
  echo "Run ./scripts/setup-dev.sh first." >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate
exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
