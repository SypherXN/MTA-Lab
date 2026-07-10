#!/usr/bin/env bash
# Generate production auth secrets and write them to api/.env (backup created).
set -euo pipefail

API_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${API_DIR}/.env"
EXAMPLE="${API_DIR}/.env.example"
FORCE=0
ROTATE_WRITE=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Sets MTA_READ_API_KEY, MTA_DASHBOARD_PASSWORD, and MTA_SESSION_SECRET when
empty or still using placeholder values. Creates ${ENV_FILE}.bak.<timestamp>.

Options:
  --force           Overwrite existing read key / password / session secret
  --rotate-write-key  Also replace MTA_WRITE_API_KEY (automation + admin)
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1 ;;
    --rotate-write-key) ROTATE_WRITE=1 ;;
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

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${EXAMPLE}" "${ENV_FILE}"
  echo "Created ${ENV_FILE} from .env.example"
fi

cp "${ENV_FILE}" "${ENV_FILE}.bak.$(date -u +%Y%m%dT%H%M%SZ)"

# shellcheck disable=SC1091
source "${ENV_FILE}"

rand_hex() {
  openssl rand -hex "${1:-24}"
}

rand_password() {
  openssl rand -base64 24 | tr -d '/+=' | head -c 24
}

set_env_var() {
  local key="$1"
  local value="$2"
  local file="$3"
  if grep -q "^${key}=" "${file}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${file}"
  else
    printf '%s=%s\n' "${key}" "${value}" >>"${file}"
  fi
}

is_placeholder_read() {
  [[ -z "${MTA_READ_API_KEY:-}" ]]
}

is_placeholder_dashboard() {
  [[ -z "${MTA_DASHBOARD_PASSWORD:-}" ]]
}

is_placeholder_session() {
  [[ -z "${MTA_SESSION_SECRET:-}" || "${MTA_SESSION_SECRET}" == "change-me-session-secret" ]]
}

is_placeholder_write() {
  [[ -z "${MTA_WRITE_API_KEY:-}" || "${MTA_WRITE_API_KEY}" == "dev-key-change-me" ]]
}

NEW_READ=""
NEW_DASHBOARD=""
NEW_SESSION=""
NEW_WRITE=""

if ((FORCE)) || is_placeholder_read; then
  NEW_READ="$(rand_hex 32)"
  set_env_var "MTA_READ_API_KEY" "${NEW_READ}" "${ENV_FILE}"
  echo "Set MTA_READ_API_KEY"
else
  echo "Keeping existing MTA_READ_API_KEY (use --force to rotate)"
  NEW_READ="${MTA_READ_API_KEY}"
fi

if ((FORCE)) || is_placeholder_dashboard; then
  NEW_DASHBOARD="$(rand_password)"
  set_env_var "MTA_DASHBOARD_PASSWORD" "${NEW_DASHBOARD}" "${ENV_FILE}"
  echo "Set MTA_DASHBOARD_PASSWORD"
else
  echo "Keeping existing MTA_DASHBOARD_PASSWORD (use --force to rotate)"
  NEW_DASHBOARD="(unchanged — not shown)"
fi

if ((FORCE)) || is_placeholder_session; then
  NEW_SESSION="$(rand_hex 32)"
  set_env_var "MTA_SESSION_SECRET" "${NEW_SESSION}" "${ENV_FILE}"
  echo "Set MTA_SESSION_SECRET"
else
  echo "Keeping existing MTA_SESSION_SECRET"
fi

if ((ROTATE_WRITE)) || is_placeholder_write; then
  NEW_WRITE="$(rand_hex 32)"
  set_env_var "MTA_WRITE_API_KEY" "${NEW_WRITE}" "${ENV_FILE}"
  echo "Set MTA_WRITE_API_KEY — update Cursor automation prompts!"
else
  echo "Keeping MTA_WRITE_API_KEY (use --rotate-write-key if still dev-key-change-me)"
  NEW_WRITE="${MTA_WRITE_API_KEY}"
fi

echo
echo "=== Next steps ==="
echo "1. Restart API:  cd ${API_DIR} && ./scripts/mta-ctl.sh restart"
echo "2. GitHub → Settings → Secrets and variables → Actions → Variables:"
echo "     MTA_API_BASE_URL = https://mta-api.matthewgtran.com"
echo "     MTA_PLANS_REPO_URL = https://github.com/SypherXN/MTA-Lab"
echo "     MTA_PLANS_REPO_BRANCH = main"
echo "     MTA_PLANS_REPO_PATH = plans"
echo "   Then: Actions → Deploy GitHub Pages Dashboard → Run workflow"
echo "   (Do not set MTA_DASHBOARD_READ_KEY — use dashboard password login below)"
echo
if [[ "${NEW_DASHBOARD}" != "(unchanged — not shown)" ]]; then
  echo "3. Dashboard login password (save now — not stored elsewhere):"
  echo "     ${NEW_DASHBOARD}"
  echo
fi
if [[ -n "${NEW_WRITE}" && "${NEW_WRITE}" != "${MTA_WRITE_API_KEY:-}" ]]; then
  echo "4. Update Cursor automation {WRITE_API_KEY} in each account's prompt."
  echo
fi
echo "Backup: ${ENV_FILE}.bak.*"
