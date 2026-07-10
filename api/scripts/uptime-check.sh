#!/usr/bin/env bash
# Local uptime probe — alerts via MTA_ALERT_WEBHOOK_URL on sustained failure.
set -euo pipefail

API_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "${API_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${API_DIR}/.env"
  set +a
fi

LOCAL_URL="${MTA_UPTIME_LOCAL_URL:-http://127.0.0.1:8000/health}"
PUBLIC_URL="${MTA_UPTIME_PUBLIC_URL:-}"
WEBHOOK="${MTA_ALERT_WEBHOOK_URL:-}"
STATE_FILE="${API_DIR}/data/uptime-check.state"
LOG_COOLDOWN_MINUTES="${MTA_UPTIME_ALERT_COOLDOWN_MINUTES:-30}"

mkdir -p "${API_DIR}/data"

check_url() {
  local url="$1"
  local body
  body="$(curl -fsS --max-time 15 "${url}" 2>&1)" || return 1
  echo "${body}" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'
}

problems=()

if ! check_url "${LOCAL_URL}"; then
  problems+=("local ${LOCAL_URL}")
fi

if [[ -n "${PUBLIC_URL}" ]] && ! check_url "${PUBLIC_URL}"; then
  problems+=("public ${PUBLIC_URL}")
fi

if ((${#problems[@]} == 0)); then
  rm -f "${STATE_FILE}"
  exit 0
fi

now_epoch="$(date +%s)"
if [[ -f "${STATE_FILE}" ]]; then
  last_epoch="$(cat "${STATE_FILE}" 2>/dev/null || echo 0)"
  if ((now_epoch - last_epoch < LOG_COOLDOWN_MINUTES * 60)); then
    echo "Health check failed (alert suppressed — ${LOG_COOLDOWN_MINUTES}m cooldown): ${problems[*]}"
    exit 1
  fi
fi

echo "${now_epoch}" >"${STATE_FILE}"
msg="MTA-Lab health check FAILED: ${problems[*]}"

if [[ -z "${WEBHOOK}" ]]; then
  echo "${msg} (set MTA_ALERT_WEBHOOK_URL to receive alerts)" >&2
  exit 1
fi

curl -fsS -X POST "${WEBHOOK}" \
  -H "Content-Type: application/json" \
  -d "$(MSG="${msg}" python3 -c 'import json,os; print(json.dumps({"text": os.environ["MSG"], "event": "uptime_check_failed", "service": "mta-lab-api", "severity": "critical"}))')" >/dev/null

echo "Alert sent: ${msg}"
exit 1
