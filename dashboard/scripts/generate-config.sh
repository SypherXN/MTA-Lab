#!/usr/bin/env bash
# Generate dashboard/config.js from environment variables (local or CI).
# GitHub Pages: set repository variables/secrets; workflow calls this script.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/config.js"

if [[ -z "${MTA_API_BASE_URL:-}" ]]; then
  echo "MTA_API_BASE_URL is required." >&2
  exit 1
fi

api_base="${MTA_API_BASE_URL}"
read_key="${MTA_DASHBOARD_READ_KEY:-}"
plans_url="${MTA_PLANS_REPO_URL:-}"
plans_branch="${MTA_PLANS_REPO_BRANCH:-main}"
plans_path="${MTA_PLANS_REPO_PATH:-plans}"

escape_js() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

{
  echo "window.MTA_CONFIG = {"
  printf '  API_BASE_URL: "%s"' "$(escape_js "$api_base")"
  if [[ -n "$read_key" ]]; then
    printf ',\n  API_READ_KEY: "%s"' "$(escape_js "$read_key")"
  fi
  if [[ -n "$plans_url" ]]; then
    printf ',\n  PLANS_REPO_URL: "%s"' "$(escape_js "$plans_url")"
    printf ',\n  PLANS_REPO_BRANCH: "%s"' "$(escape_js "$plans_branch")"
    printf ',\n  PLANS_REPO_PATH: "%s"' "$(escape_js "$plans_path")"
  fi
  echo ""
  echo "};"
} >"${OUT}"

echo "Wrote ${OUT}"
