#!/usr/bin/env bash
# MTA-Lab operator CLI — status, updates, backups, service control.
set -euo pipefail

API_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_DIR="$(cd "${API_DIR}/.." && pwd)"
SERVICE_NAME="${MTA_SERVICE_NAME:-mta-lab-api}"

load_env() {
  if [[ -f "${API_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${API_DIR}/.env"
    set +a
  fi
}

service_installed() {
  systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null &&
    systemctl cat "${SERVICE_NAME}.service" &>/dev/null
}

require_service() {
  if ! service_installed; then
    echo "Systemd service '${SERVICE_NAME}' is not installed." >&2
    echo "Run: ${API_DIR}/deploy/install-service.sh" >&2
    exit 1
  fi
}

cmd_health() {
  load_env
  local url="${1:-http://127.0.0.1:8000/health}"
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required for health checks." >&2
    exit 1
  fi
  echo "GET ${url}"
  curl -fsS "${url}" | { command -v jq >/dev/null && jq . || cat; }
  echo
}

cmd_status() {
  echo "Repo:    ${REPO_DIR}"
  echo "API dir: ${API_DIR}"
  echo
  if service_installed; then
    systemctl is-enabled "${SERVICE_NAME}.service" 2>/dev/null || true
    systemctl is-active "${SERVICE_NAME}.service" 2>/dev/null || true
    echo
    systemctl status "${SERVICE_NAME}.service" --no-pager -l || true
  else
    echo "Systemd: not installed (dev mode or run install-service.sh)"
    if pgrep -af "uvicorn app.main:app" >/dev/null 2>&1; then
      echo
      echo "Manual uvicorn process(es):"
      pgrep -af "uvicorn app.main:app" || true
    fi
  fi
  echo
  cmd_health || echo "Health check failed."
}

cmd_logs() {
  require_service
  local follow="${1:-}"
  if [[ "${follow}" == "-f" || "${follow}" == "--follow" ]]; then
    journalctl -u "${SERVICE_NAME}.service" -f
  else
    journalctl -u "${SERVICE_NAME}.service" -n "${follow:-80}" --no-pager
  fi
}

cmd_start() {
  require_service
  sudo systemctl start "${SERVICE_NAME}.service"
  cmd_health
}

cmd_stop() {
  require_service
  sudo systemctl stop "${SERVICE_NAME}.service"
}

cmd_restart() {
  require_service
  sudo systemctl restart "${SERVICE_NAME}.service"
  sleep 1
  cmd_health
}

cmd_backup() {
  exec "${API_DIR}/scripts/backup-db.sh" "$@"
}

cmd_sync_plans() {
  cd "${API_DIR}"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  exec python3 scripts/sync_plans_from_repo.py "$@"
}

cmd_update() {
  exec "${API_DIR}/deploy/update.sh" "$@"
}

cmd_install_service() {
  exec "${API_DIR}/deploy/install-service.sh" "$@"
}

cmd_install_cron() {
  exec "${API_DIR}/deploy/install-cron.sh" "$@"
}

cmd_install_nginx() {
  exec "${API_DIR}/deploy/install-nginx.sh" "$@"
}

cmd_secure_env() {
  exec "${API_DIR}/deploy/secure-env.sh" "$@"
}

cmd_uptime_check() {
  exec "${API_DIR}/scripts/uptime-check.sh" "$@"
}

cmd_production_hardening() {
  exec "${API_DIR}/deploy/production-hardening.sh" "$@"
}

cmd_retention() {
  load_env
  local dry_run="${1:-false}"
  local key="${MTA_WRITE_API_KEY:-}"
  if [[ -z "${key}" ]]; then
    echo "MTA_WRITE_API_KEY must be set in ${API_DIR}/.env" >&2
    exit 1
  fi
  curl -fsS -X POST "http://127.0.0.1:8000/api/admin/retention/run" \
    -H "X-API-Key: ${key}" \
    -H "Content-Type: application/json" \
    -d "{\"dry_run\": ${dry_run}}" | { command -v jq >/dev/null && jq . || cat; }
  echo
}

usage() {
  cat <<EOF
MTA-Lab operator CLI

Usage: $(basename "$0") <command> [options]

Service (requires systemd — run install-service first):
  status              Show service state + health
  health              GET /health
  start               Start API service
  stop                Stop API service
  restart             Restart API service
  logs [N|-f]         Show last N log lines (default 80) or follow (-f)

Maintenance:
  backup              Run SQLite backup (scripts/backup-db.sh)
  sync-plans          Import plans/*.json into the database
  update [opts]       git pull, deps, sync plans, restart — see update.sh
  retention           POST retention run (dry_run=false)
  retention-dry         POST retention run (dry_run=true)

Setup:
  install-service     Install/refresh systemd unit (auto-start on boot)
  install-nginx       Enable nginx on boot + reload config
  install-cron        Install backup + retention cron (--with-uptime optional)
  secure-env          Generate read key + dashboard password in .env
  production-harden   nginx + secure-env + uptime cron + restart (pass public /health URL)
  uptime-check        Run health probe now (alerts via webhook)

Environment:
  MTA_SERVICE_NAME    systemd unit name (default: mta-lab-api)

Examples:
  $(basename "$0") status
  $(basename "$0") update
  $(basename "$0") update --no-pull
  $(basename "$0") logs -f
EOF
}

main() {
  local cmd="${1:-help}"
  shift || true
  case "${cmd}" in
    status) cmd_status "$@" ;;
    health) cmd_health "$@" ;;
    start) cmd_start "$@" ;;
    stop) cmd_stop "$@" ;;
    restart) cmd_restart "$@" ;;
    logs) cmd_logs "$@" ;;
    backup) cmd_backup "$@" ;;
    sync-plans) cmd_sync_plans "$@" ;;
    update) cmd_update "$@" ;;
    install-service) cmd_install_service "$@" ;;
    install-cron) cmd_install_cron "$@" ;;
    install-nginx) cmd_install_nginx "$@" ;;
    secure-env) cmd_secure_env "$@" ;;
    uptime-check) cmd_uptime_check "$@" ;;
    production-harden) cmd_production_hardening "$@" ;;
    production-hardening) cmd_production_hardening "$@" ;;
    retention) cmd_retention "false" ;;
    retention-dry) cmd_retention "true" ;;
    help|-h|--help) usage ;;
    *)
      echo "Unknown command: ${cmd}" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
