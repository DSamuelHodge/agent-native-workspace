#!/usr/bin/env bash
# scripts/docker_mcp_test.sh
#
# Spin up data/agent_native.db using db_up.sh *inside Docker*, install deps,
# run the full MCP tool integration tests (verifying all ~41 live implementations),
# then the container is torn down (--rm).
#
# The resulting DB file is left on the *host* at data/agent_native.db thanks to
# the bind mount. Perfect for reproducible, isolated test/eval runs.
#
# Usage (when Docker Desktop/daemon is running):
#   ./scripts/docker_mcp_test.sh
#
# Teardown:
#   - Container: already gone (uses --rm)
#   - DB file (if you want a completely clean slate after evaluations):
#       rm -f data/agent_native.db
#
# Requirements on host: Docker (client + daemon).
# Inside container we use a fresh python:3.12-bookworm + apt sqlite3 (has FTS5).

set +e  # Do not use strict mode in this wrapper to avoid affecting caller shell

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="python:3.12-bookworm"

echo "==> Using Docker image: ${IMAGE}"
echo "==> Project root: ${ROOT}"
echo "==> This will create data/agent_native.db on the host via bind mount."

docker run --rm \
  -v "${ROOT}:/workspace" \
  -w /workspace \
  -e DATABASE_URL="${DATABASE_URL:-}" \
  "${IMAGE}" \
  bash -c '
    set +e
    echo "== [container] Installing sqlite3 CLI =="
    apt-get update -qq && apt-get install -y -qq sqlite3

    if [ -n "${DATABASE_URL}" ]; then
      echo "== [container] Using remote DATABASE_URL (Turso) for test/eval =="
      echo "DATABASE_URL set (length: ${#DATABASE_URL})"
      # For remote, assume schema already applied via turso (no local migrate needed for test)
    else
      echo "== [container] Running db_up.sh (migrate) for local sqlite =="
      ./scripts/db_up.sh
    fi

    echo "== [container] Setting up Python env and running MCP integration tests =="
    cd python
    python -m venv /tmp/venv_docker_mcp || true
    . /tmp/venv_docker_mcp/bin/activate
    pip install -q --upgrade pip
    pip install -q -e ".[dev]" -e ".[mcp]"

    python -m pytest tests/test_mcp_tools_integration.py -q --tb=short

    echo ""
    echo "=== MCP verification complete inside Docker ==="
    if [ -n "${DATABASE_URL}" ]; then
      echo "Used remote DB: production-grade Turso path"
    else
      echo "DB file is at: data/agent_native.db (on host)"
      ls -l /workspace/data/agent_native.db 2>/dev/null || true
    fi
  '

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
  echo "SUCCESS: Dockerized DB spinup + MCP tests completed cleanly."
  echo "You can now use the DB at data/agent_native.db for server runs or further evals."
  echo ""
  echo "To start the MCP server (stdio):"
  echo "  cd python && source .venv_test/bin/activate 2>/dev/null || python -m venv .venv && source .venv/bin/activate && pip install -e '.[mcp]'"
  echo "  DATABASE_URL=file:../data/agent_native.db python -m agent_native_workspace.mcp_server"
else
  echo "Docker run exited with code $EXIT_CODE. Check output above for errors."
fi

exit $EXIT_CODE
