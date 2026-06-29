#!/usr/bin/env bash
# Install MTA-Lab API on Oracle Linux / Ubuntu (OCI VM).
set -euo pipefail

INSTALL_USER="${INSTALL_USER:-opc}"
INSTALL_DIR="${INSTALL_DIR:-/home/${INSTALL_USER}/MTA-Lab}"
API_DIR="${INSTALL_DIR}/api"

echo "Installing MTA-Lab API to ${API_DIR}"

sudo mkdir -p "${API_DIR}"
sudo chown -R "${INSTALL_USER}:${INSTALL_USER}" "${INSTALL_DIR}" 2>/dev/null || true

cd "${API_DIR}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created ${API_DIR}/.env — edit secrets before going live."
fi

mkdir -p data/backups
chmod +x scripts/*.sh scripts/*.py 2>/dev/null || true

echo ""
echo "Next steps:"
echo "  1. Edit ${API_DIR}/.env (WRITE_API_KEY, READ_API_KEY, CORS_ORIGINS, ALERT_WEBHOOK_URL)"
echo "  2. sudo cp deploy/mta-lab-api.service.example /etc/systemd/system/mta-lab-api.service"
echo "  3. sudo sed -i 's|/home/opc/MTA-Lab|${INSTALL_DIR}|g' /etc/systemd/system/mta-lab-api.service"
echo "  4. sudo systemctl daemon-reload && sudo systemctl enable --now mta-lab-api"
echo "  5. sudo cp deploy/nginx.conf.example /etc/nginx/conf.d/mta-lab-api.conf (edit server_name)"
echo "  6. Add cron: scripts/backup-db.sh (daily) and scripts/price_watcher.py (intraday)"
echo ""
echo "Health check: curl http://127.0.0.1:8000/health"
