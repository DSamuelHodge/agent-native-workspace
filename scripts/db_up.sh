#!/usr/bin/env bash
# Create local libSQL/SQLite DB and apply canonical DDL.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT/data}"
DB_PATH="${DB_PATH:-$DATA_DIR/agent_native.db}"
mkdir -p "$DATA_DIR"
if [[ ! -f "$DB_PATH" ]]; then
  sqlite3 "$DB_PATH" < "$ROOT/schema/001_init.sql"
  echo "created $DB_PATH"
else
  VER="$(sqlite3 "$DB_PATH" "SELECT version FROM schema_migrations WHERE version='001_init';" 2>/dev/null || true)"
  if [[ -z "$VER" ]]; then
    sqlite3 "$DB_PATH" < "$ROOT/schema/001_init.sql"
    echo "migrated $DB_PATH"
  else
    echo "already migrated: $DB_PATH"
  fi
fi
echo "DATABASE_URL=file:${DB_PATH}"
sqlite3 "$DB_PATH" "PRAGMA foreign_keys=ON; SELECT count(*) AS tables FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
