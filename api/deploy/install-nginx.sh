#!/usr/bin/env bash
# Enable nginx on boot and validate config (TLS via certbot is manual).
set -euo pipefail

API_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NGINX_CONF_NAME="${MTA_NGINX_CONF_NAME:-mta-lab-api.conf}"
NGINX_CONF="/etc/nginx/conf.d/${NGINX_CONF_NAME}"
EXAMPLE="${API_DIR}/deploy/nginx.conf.example"

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx is not installed." >&2
  echo "  Oracle Linux: sudo dnf install -y nginx" >&2
  echo "  Ubuntu:       sudo apt install -y nginx" >&2
  exit 1
fi

if [[ ! -f "${NGINX_CONF}" && -f "${EXAMPLE}" ]]; then
  echo "No ${NGINX_CONF} — copying example (edit server_name, then certbot)."
  sudo cp "${EXAMPLE}" "${NGINX_CONF}"
  echo "Edit: sudo nano ${NGINX_CONF}"
fi

sudo systemctl enable nginx
sudo systemctl start nginx

if sudo nginx -t; then
  sudo systemctl reload nginx
else
  echo "nginx config test failed — fix ${NGINX_CONF} before relying on HTTPS." >&2
  exit 1
fi

echo "nginx enabled on boot and reloaded."
systemctl is-enabled nginx
systemctl is-active nginx
