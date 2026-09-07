#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="${DB_PATH:-$ROOT/data/agent_native.db}"
export DATABASE_URL="${DATABASE_URL:-file:$DB}"

"$ROOT/scripts/db_up.sh" >/dev/null

echo "== catalog =="
MISSING="$(sqlite3 "$DB" < "$ROOT/evals/catalog_check.sql")"
if [[ -n "${MISSING}" ]]; then
  echo "Missing tables:" >&2
  echo "${MISSING}" >&2
  exit 1
fi
echo "catalog ok"

echo "== pytest =="
cd "$ROOT/python"
# shellcheck disable=SC1091
source .venv/bin/activate
pytest -q

echo "== drizzle/ts =="
cd "$ROOT/ts"
npm test --silent

echo "ALL GREEN"
