#!/usr/bin/env bash
# One-shot production hardening: nginx boot, auth secrets, uptime cron.
set -euo pipefail

API_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_URL="${1:-}"

echo "==> 1/4 Secure .env (read key + dashboard password + session secret)"
"${API_DIR}/deploy/secure-env.sh"

echo
echo "==> 2/4 Enable nginx on boot"
"${API_DIR}/deploy/install-nginx.sh"

echo
echo "==> 3/4 Install maintenance + uptime cron"
if [[ -n "${PUBLIC_URL}" ]]; then
  if grep -q '^MTA_UPTIME_PUBLIC_URL=' "${API_DIR}/.env" 2>/dev/null; then
    sed -i "s|^MTA_UPTIME_PUBLIC_URL=.*|MTA_UPTIME_PUBLIC_URL=${PUBLIC_URL}|" "${API_DIR}/.env"
  else
    echo "MTA_UPTIME_PUBLIC_URL=${PUBLIC_URL}" >>"${API_DIR}/.env"
  fi
fi
"${API_DIR}/deploy/install-cron.sh" --with-uptime

echo
echo "==> 4/4 Restart API to pick up new secrets"
if systemctl cat mta-lab-api.service &>/dev/null; then
  sudo systemctl restart mta-lab-api.service
  sleep 2
  curl -fsS http://127.0.0.1:8000/api/auth/status || true
  echo
fi

cat <<EOF

Production hardening complete.

Manual follow-ups:
  • certbot: sudo certbot --nginx -d YOUR_DOMAIN (if not done)
  • dashboard/config.js: add API_READ_KEY from secure-env output (or use login password)
  • Cursor automations: update WRITE_API_KEY in each prompt
  • External monitor: see .local/uptime-external-setup.md (UptimeRobot)
  • Updates: run ./scripts/mta update manually — never cron git pull

EOF
