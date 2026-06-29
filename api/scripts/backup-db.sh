#!/usr/bin/env bash
# Create a consistent SQLite backup of the MTA-Lab database.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DB_PATH="${MTA_DATABASE_PATH:-./data/mta_lab.db}"
BACKUP_DIR="${MTA_BACKUP_DIR:-./data/backups}"
KEEP="${MTA_BACKUP_KEEP:-14}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/mta_lab_${TIMESTAMP}.db"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$DEST'"
else
  cp "$DB_PATH" "$DEST"
  echo "Warning: sqlite3 CLI not found; used file copy (less safe under write load)." >&2
fi

echo "Backup written: $DEST"

mapfile -t BACKUPS < <(ls -1t "$BACKUP_DIR"/mta_lab_*.db 2>/dev/null || true)
if ((${#BACKUPS[@]} > KEEP)); then
  for old in "${BACKUPS[@]:KEEP}"; do
    rm -f "$old"
    echo "Pruned old backup: $old"
  done
fi
