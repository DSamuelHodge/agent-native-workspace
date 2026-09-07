# agent-native-workspace

Agent-first workspace data model (Macro MCP reverse-engineer) with **libSQL/SQLite** as the canonical on-device engine. SQLAlchemy + Drizzle share one DDL. Optional Turso remote URL for agents/bots.

## Why libSQL (not Postgres on-device)

This Termux/PRoot environment cannot run stock Postgres reliably (f2fs ignores `chown`). libSQL/SQLite is embedded, FTS5-capable, and Turso-compatible for remote agents.

## Quick start

```sh
./scripts/db_up.sh
# DATABASE_URL=file:.../data/agent_native.db
```

### Python

```sh
cd python
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

### TypeScript (Drizzle + @libsql/client)

```sh
cd ts && npm install && npm test
```

### Evals

```sh
./evals/run.sh
```

## Design

- **Entities + extensions** (document, channel, chat, call, email_thread, company, reminder)
- Tasks/skills = documents + properties / `skill_flags`
- Property uniqueness: personal vs team partial unique indexes
- Search: FTS5 tables `search_name_fts` / `search_content_fts`
- UUIDs are application-supplied TEXT

Remote Turso: set `DATABASE_URL=libsql://...` (TS client ready; Python uses local sqlite file by default).
