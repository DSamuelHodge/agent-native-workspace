# agent-native-workspace

Agent-first workspace data model (Macro MCP reverse-engineer) with **libSQL/SQLite** as the canonical on-device engine. SQLAlchemy + Drizzle share one DDL. Optional Turso remote URL for agents/bots.

Implements a **stateless MCP server** (2026-07-28 conventions) exposing ~67+ Macro.com-style tools over the workspace for agent-native use.

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

# Run as MCP server (stdio, for Claude Desktop / Codex / etc.)
python -m agent_native_workspace.mcp_server
```

With `mcp` extra for full SDK support:

```sh
pip install -e '.[mcp]'
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
- Search: FTS5 tables `search_name_fts` / `search_content_fts` (kept separate to match NameSearch vs ContentSearch)
- UUIDs are application-supplied TEXT
- Generic property system (typed values + multi-select/options) powers Status/Priority/Tags/CRM Stage/Owner + arbitrary custom fields
- Mentions/backlinks as first-class graph
- Activity log attributes agent actions to the user

Remote Turso: set `DATABASE_URL=libsql://...` (TS client ready; Python uses local sqlite file by default).

## MCP Server & Stateless Conventions (2026-07-28)

This project follows the latest stateless MCP model (SEP-2575, SEP-2567, 2026-07-28 spec):

- No `initialize`/`initialized` handshake and no `Mcp-Session-Id`.
- Every request is self-contained: include `MCP-Protocol-Version: 2026-07-28` header (HTTP) + `_meta.io.modelcontextprotocol/protocolVersion`.
- `server/discover` is implemented (and recommended as first call for capabilities).
- Streamable HTTP is served **stateless by default** (per-request server factory / no pinned sessions). Use `SessionMode.Stateless`.
- Routing headers: `Mcp-Method` and `Mcp-Name` on Streamable HTTP POSTs.
- List results (`tools/list` etc.) include `ttlMs`, `cacheScope`, and are returned in deterministic order.
- Results include `resultType` ("complete" | "input_required" for MRTR).
- Server-to-client requests use Multi Round-Trip Requests (MRTR) when needed.
- Tools/resources/prompts are **not** session-scoped; cross-call state uses explicit handles passed as tool arguments.

Run the server:
- stdio (recommended for local agents): `python -m agent_native_workspace.mcp_server`
- HTTP: the server exposes a stateless handler (see source for `createMcpHandler` / equivalent factory usage).

Add to your client (example):

```json
{
  "mcpServers": {
    "agent-native": {
      "command": "python",
      "args": ["-m", "agent_native_workspace.mcp_server"],
      "cwd": ".../agent-native-workspace/python"
    }
  }
}
```

Tool surface: modeled 1:1 on Macro's ~67 tools (ListEntities, ReadContent, SetEntityProperty, searches, CRUD for docs/projects/channels/reminders/bots, email label ops, calendar, CRM, activity, web/code exec helpers, Subagent, etc.). See `docs/agent_native_workspace_schema.md` and the server tool registry for the exact catalog.

## Conventions

- **Polymorphic entities**: All first-class things (docs, projects, channels, chats, calls, emails, companies, reminders) are rows in `entities` + type-specific extension table. `entity_type` enum drives behavior.
- **Tasks & Skills**: Just `document` entities + property flags or `skill_flags`. No separate tables.
- **Properties**: One generic typed system (`entity_properties` + options). System properties (Status, Assignees, Stage, ...) use well-known UUIDs for direct `SetEntityProperty` without `GetEntityProperties` first.
- **Tags**: `property_definition` rows with `is_tag=1`; matched by label; apply via `add_option_ids`/`remove_option_ids` deltas (never full overwrite for multi-select).
- **Search**: Two independent indexes (name/title FTS vs body/content FTS) because Macro exposes distinct `NameSearch` and `ContentSearch`.
- **Activity attribution**: `activity_log.actor='agent'` actions are still attributed to the `user_id` for permissions; include `agent_session_id` when you need replay/debug.
- **Permissions**: Derived from channel membership / ownership (no per-object ACLs in the core model).
- **Bots vs agent chats**: Separate (bots = stable webhook actors; chats = conversational sessions). Collapsible in pure headless setups.
- Stateless MCP: handlers must be safe to run against a fresh DB session per request; do not rely on in-memory connection state across calls.

## Production

This workspace is production-grade ready:

- **Docker spin-up for tests/evals**: `./scripts/docker_mcp_test.sh` (requires local Docker daemon). Uses bind mount for reproducible DB.
  - For Turso remote: `DATABASE_URL=libsql://...?... python ...` or pass `-e` in the script.
  - Alternative prod image: `docker build -f Dockerfile -t agent-native-mcp .` then `docker run -e DATABASE_URL=... agent-native-mcp`
- **Turso / libSQL remote**: Set `DATABASE_URL=libsql://agent-native-workspace-hodgederrick.aws-us-west-2.turso.io?authToken=...`
  - Install extra: `pip install -e '.[turso]'` (provides sqlalchemy-libsql for remote dialect).
  - Schema applied to the DB; FTS5 supported on Turso.
- **FTS auto-maintenance**: `CreateDocument`, `RenameDocument`, `EditDocument`, `CreateProject` keep `search_name_fts` / `search_content_fts` in sync automatically (no manual seeds needed for NameSearch/ContentSearch).
- **Observability**: basic `logging.getLogger(__name__)` calls on mutations.
- **Activity attribution**: `_log_activity` emits to `activity_log` for create_document / create_project / create_reminder (extend to other mutators as needed).
- **Transactions**: all mutating tools issue `session.commit()` (wrap in try/rollback for stricter prod if desired).
- **Auth note**: current impl uses demo-user bootstrap (`_get_or_create_demo_user`). For real multi-user, pass identity via per-request context/headers and enforce in handlers.
- **Stubs**: remaining Macro tools (WebSearch, SendEmail, Subagent, etc.) are catalog entries only; implement or document as "external delegate" for your host.

See `docs/agent_native_workspace_schema.md` and `python/src/agent_native_workspace/mcp_server.py` (TOOLS_CATALOG + IMPLEMENTED).

To run integration tests against Turso:

```sh
DATABASE_URL=libsql://...?... ./scripts/docker_mcp_test.sh
# or locally after pip install -e '.[turso]'
```
