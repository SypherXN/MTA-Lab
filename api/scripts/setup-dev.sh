#!/usr/bin/env bash
# Bootstrap MTA-Lab API dev environment (WSL/Ubuntu).
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11+ first." >&2
  exit 1
fi

if ! dpkg -s python3-venv >/dev/null 2>&1; then
  echo "python3-venv is not installed."
  echo "Run: sudo apt install -y python3-venv python3-pip"
  if [[ ! -d .venv ]]; then
    exit 1
  fi
  echo "Continuing with existing .venv..."
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Dev environment ready. Activate with: source .venv/bin/activate"
echo "Run tests: ./test.sh"
