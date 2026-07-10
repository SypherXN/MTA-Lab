#!/usr/bin/env bash
# Install opc user crontab entries for MTA-Lab backup + retention (+ optional uptime).
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
API_DIR="${INSTALL_DIR}/api"
MARKER="# mta-lab-maintenance"
WITH_UPTIME=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-uptime) WITH_UPTIME=1 ;;
    -h | --help)
      echo "Usage: $(basename "$0") [--with-uptime]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ ! -f "${API_DIR}/.env" ]]; then
  echo "Missing ${API_DIR}/.env" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${API_DIR}/.env"

WRITE_KEY="${MTA_WRITE_API_KEY:-}"
if [[ -z "${WRITE_KEY}" ]]; then
  echo "MTA_WRITE_API_KEY must be set in .env for retention cron." >&2
  exit 1
fi

BACKUP_SH="${API_DIR}/scripts/backup-db.sh"
UPTIME_SH="${API_DIR}/scripts/uptime-check.sh"
CTL_SH="${API_DIR}/scripts/mta-ctl.sh"

UPTIME_LINE=""
if ((WITH_UPTIME)); then
  UPTIME_LINE="*/5 * * * * ${UPTIME_SH} >> ${API_DIR}/data/uptime.log 2>&1"
fi

NEW_BLOCK=$(cat <<EOF
${MARKER}
# MTA-Lab: no automatic git pull — run ./scripts/mta update manually after reviewing changes
0 3 * * * ${BACKUP_SH} >> ${API_DIR}/data/backup.log 2>&1
0 4 * * 0 curl -fsS -X POST http://127.0.0.1:8000/api/admin/retention/run -H "X-API-Key: ${WRITE_KEY}" -H "Content-Type: application/json" -d '{"dry_run":false}' >> ${API_DIR}/data/retention.log 2>&1
${UPTIME_LINE}
EOF
)

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "${EXISTING}" | grep -vF "${MARKER}" | grep -vF "${BACKUP_SH}" | grep -vF "${UPTIME_SH}" | grep -v 'retention/run' | grep -v 'no automatic git pull' | sed '/^[[:space:]]*$/d' || true)"
{
  [[ -n "${FILTERED}" ]] && printf '%s\n' "${FILTERED}"
  printf '%s\n' "${NEW_BLOCK}"
} | crontab -

echo "Installed crontab entries:"
echo "${NEW_BLOCK}"
echo
echo "Verify: crontab -l"
echo "Manual backup: ${BACKUP_SH}"
echo "Manual retention: ${CTL_SH} retention"
echo "Manual update:    ${INSTALL_DIR}/scripts/mta update  (never scheduled via cron)"
