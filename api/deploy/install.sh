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
chmod +x scripts/*.sh scripts/*.py deploy/*.sh 2>/dev/null || true

echo ""
echo "Next steps:"
echo "  1. Edit ${API_DIR}/.env (WRITE_API_KEY, READ_API_KEY, CORS_ORIGINS, ALERT_WEBHOOK_URL)"
echo "  2. ./deploy/install-service.sh     # systemd: auto-start on boot + restart on crash"
echo "  3. ./deploy/install-cron.sh        # optional: daily backup + weekly retention"
echo "  4. sudo cp deploy/nginx.conf.example /etc/nginx/conf.d/mta-lab-api.conf (edit server_name)"
echo ""
echo "Day-to-day: ./scripts/mta-ctl.sh status | update | logs -f"
echo "Health check: curl http://127.0.0.1:8000/health"
