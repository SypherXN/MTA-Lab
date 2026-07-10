#!/usr/bin/env bash
# Install systemd unit for MTA-Lab API (auto-start on boot, restart on crash).
set -euo pipefail

INSTALL_USER="${INSTALL_USER:-$(whoami)}"
INSTALL_DIR="${INSTALL_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
API_DIR="${INSTALL_DIR}/api"
SERVICE_NAME="${MTA_SERVICE_NAME:-mta-lab-api}"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ ! -f "${API_DIR}/.venv/bin/uvicorn" ]]; then
  echo "API venv not found at ${API_DIR}/.venv — run deploy/install.sh first." >&2
  exit 1
fi

if [[ ! -f "${API_DIR}/.env" ]]; then
  echo "Missing ${API_DIR}/.env — copy from .env.example and configure secrets." >&2
  exit 1
fi

echo "Installing ${SERVICE_NAME}.service"
echo "  User:  ${INSTALL_USER}"
echo "  API:   ${API_DIR}"

TMP="$(mktemp)"
sed \
  -e "s|/home/opc/MTA-Lab|${INSTALL_DIR}|g" \
  -e "s|^User=opc|User=${INSTALL_USER}|g" \
  "${API_DIR}/deploy/mta-lab-api.service.example" >"${TMP}"

sudo cp "${TMP}" "${UNIT_PATH}"
rm -f "${TMP}"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo
echo "Installed and started ${SERVICE_NAME}.service"
echo "  status:  systemctl status ${SERVICE_NAME}"
echo "  logs:    journalctl -u ${SERVICE_NAME} -f"
echo "  health:  curl http://127.0.0.1:8000/health"
echo
systemctl is-active "${SERVICE_NAME}.service" || true
