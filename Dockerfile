# Production-grade Dockerfile for agent-native-workspace MCP server
# Supports local SQLite or Turso/libSQL via DATABASE_URL
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for sqlite + build if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python package with mcp extra
COPY python/pyproject.toml python/
COPY python/src/ python/src/
RUN pip install -e './python[mcp,turso]'

# Copy scripts and schema for migrate if needed
COPY schema/ /app/schema/
COPY scripts/ /app/scripts/
COPY python/src/agent_native_workspace/migrate.py /app/

# Default to stdio MCP server
# For Turso: docker run -e DATABASE_URL=libsql://...-hodgederrick.aws-us-west-2.turso.io?authToken=xxx ...
# For local test: uses file DB or mounted volume
ENTRYPOINT ["python", "-m", "agent_native_workspace.mcp_server"]
