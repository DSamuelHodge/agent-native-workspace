# Agent-Native Workspace — Schema Reverse-Engineered from Macro's MCP Tool Surface

Source: the 67+ tools exposed at `https://mcp-server.macro.com/mcp` (full list at
`docs.macro.com/llms.txt`). This doc infers the underlying data model purely from
tool names, parameters, and descriptions, then proposes a Postgres schema for a
GUI-less, agent-first clone.

---

## 1. The core insight

`GetEntityProperties` and `SetEntityProperty` both state: *"Tasks are targeted as
entity_type='document'."* Tasks are not a first-class table — they're documents
with a `Status` / `Priority` / `Assignee` property set attached. Skills are the
same trick again: `ListSkills` describes them as "markdown documents containing
instructions," read via the plain `ReadContent` document tool.

So the real model isn't "one table per feature." It's:

- a **small set of base entity types** (document, project, channel, chat, call,
  email_thread, company)
- a **generic property system** bolted onto any entity (status, priority, tags,
  custom fields — all through the same `SetEntityProperty` shape)
- a **generic mention/backlink graph** connecting any entity to any entity
- **channel-membership-derived permissions**, not per-object ACLs

Everything else (tasks, tags, CRM stages, skills) is a *configuration* of that
core, not a new table. This is what lets one tool (`SetEntityProperty`) cover
tasks, CRM records, and arbitrary documents at once, and what lets `ListEntities`
/ `ContentSearch` / `NameSearch` work identically across types.

---

## 2. Tool → concept mapping

| Tool(s) | Reveals |
|---|---|
| `CreateDocument`, `EditDocument`, `ReadContent`, `ReadMetadata`, `RenameDocument` | Documents have separate **content** (markdown body, patchable in place) vs **metadata** (name, etc.) — two read paths, one write-in-place path. `EditDocument` is explicitly scoped to markdown docs, not uploaded files (PDF/DOCX/XLSX), implying an `is_editable` / `source_type` distinction. |
| `GetEntityProperties`, `SetEntityProperty`, `BulkSetEntityPropertyOptions` | Properties are **typed** (the tool needs "exactly one value field matching the property's data type") and **scoped** (personal vs team). Multi-select properties (tags) use an options-delta pattern, not full overwrite. |
| `ListTags`, `CreateTag`, `EditTag`, `DeleteTag` | Tags = a specific `property_definition` flavor with `is_tag=true`, its own color, matched by label not id — i.e., tags are looked up before creation to avoid dupes. |
| `ListEntities`, `ContentSearch`, `NameSearch` | Two independent keyword indexes: one over **titles/names**, one over **body content** (doc text, email subject/body/sender, chat messages, call transcripts) — separate tools, so likely separate indexes/tables, not one blended search. |
| `CreateProject`, `ReadProject`, `MoveToProject` | Projects are foldering, nestable, and can contain documents, chats, *and other projects* — a self-referential tree. |
| `GetThread`, `ListInboxes`, `ListLabels`, `UpdateThreadLabels`, `SetSenderPolicy` | Email model is Gmail-shaped: everything (archive/read/star/spam) is a **label add/remove** operation, not distinct state fields. Multi-inbox with primary/delegated flags. |
| `CreateChannel`, `RenameChannel`, `ManageChannelParticipants`, `ReadChannelMessages`, `ReadChannelThread`, `ReadChannelMessageContext` | Channels have types (private/team/dm), DMs can't be renamed or have membership changed, messages support **threaded replies** as a parent/child self-reference, and there's a windowed-read pattern (latest N, cursor, or "context around message X") distinct from full-thread reads. |
| `ReadChat`, `Subagent` | Agent conversations are their own entity with `role`-tagged messages and attachment references — structurally identical to channel messages but a separate table (agent chats vs human channels). |
| `ReadCallRecord` | Calls store transcripts as **segments** with `speakerId` + timing, separate from call metadata (duration, participants) which lives on `ListEntities`. |
| `GetCompany`, `ListCompanies` | CRM companies have domains (plural), a fixed pipeline shape (Stage/Owner/Revenue) *plus* arbitrary custom properties via the same property system, plus attached contacts. |
| `CreateBot`, `ConfigureBot`, `IssueBotCredential`, `GetBotWebhooks`, `ManageBotChannelAccess` | Bots are distinct from agent chats: they have stable handles, per-channel webhook URLs, and credentials issued (not returned) via a separate mint step — i.e., secrets aren't stored in plaintext, only a reference/hash is queryable. |
| `CreateReminder`, `ListReminders`, `UpdateReminder`, `DeleteReminder` | Reminders are either **attached** to an entity or standalone, filtered by `completed` by default — a soft-done flag, not deletion, is the normal "I dealt with this" path. |
| `MarkNotificationsDone`, `MarkNotificationsSeen` | Notifications have two independent boolean-ish states: seen vs done — read receipts and completion are tracked separately. |
| `ListImportEntities`, `DeleteImportEntity`, `ImportNotionPage` | An import ledger with states (staged/in_flight/imported/declined) exists *before* items become real entities — imports are staged, not applied directly. |
| `ReadActivity` | A first-class audit log, queryable by actor and time range, that also logs actions **agents took on the user's behalf** — property changes log both `fromLabels`/`toLabels`. |
| `SearchTools`, `LoadTools` | Third-party integration tools are not all loaded by default — they're discovered by keyword search and loaded on demand, which is why the "67+" figure is a floor, not a ceiling. |

---

## 3. Proposed Postgres schema

```sql
-- ============================================================
-- CORE: users, teams, membership
-- ============================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE teams (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE team_role AS ENUM ('owner', 'admin', 'member');

CREATE TABLE team_members (
    team_id         UUID REFERENCES teams(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    role            team_role NOT NULL DEFAULT 'member',
    invited_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    joined_at       TIMESTAMPTZ,
    PRIMARY KEY (team_id, user_id)
);

-- ============================================================
-- ENTITIES: the polymorphic base every mentionable/taggable
-- thing shares (documents, projects, channels, chats, calls,
-- email threads, companies). Extension tables hold type-specific
-- columns; entities holds what's common: identity, ownership,
-- naming, timestamps, soft-delete.
-- ============================================================

CREATE TYPE entity_type AS ENUM (
    'document', 'project', 'channel', 'chat',
    'call', 'email_thread', 'company', 'reminder'
);

CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     entity_type NOT NULL,
    team_id         UUID REFERENCES teams(id),        -- NULL = personal
    owner_id        UUID REFERENCES users(id) NOT NULL,
    name            TEXT,                              -- title/subject/display name
    parent_project_id UUID REFERENCES entities(id),    -- foldering, any entity type
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_entities_team_type ON entities(team_id, entity_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_entities_parent ON entities(parent_project_id) WHERE deleted_at IS NULL;

-- ============================================================
-- DOCUMENTS (covers plain docs, tasks, and skills — the
-- differentiator is which properties/tags are attached, not
-- a different table)
-- ============================================================

CREATE TYPE document_source AS ENUM ('native', 'uploaded_pdf', 'uploaded_docx', 'uploaded_xlsx', 'imported');

CREATE TABLE documents (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    content_md      TEXT NOT NULL DEFAULT '',   -- markdown body; swap for CRDT blob column if collaborative
    source          document_source NOT NULL DEFAULT 'native',
    is_editable     BOOLEAN NOT NULL DEFAULT TRUE  -- false for uploaded PDFs/DOCX/XLSX per EditDocument's own scoping
);

-- ============================================================
-- PROPERTY SYSTEM: generic typed fields attachable to any
-- entity. Tags are just property_definitions with is_tag=true.
-- ============================================================

CREATE TYPE property_data_type AS ENUM (
    'text', 'number', 'date', 'boolean',
    'select', 'multi_select', 'user_ref'
);

CREATE TABLE property_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id         UUID REFERENCES teams(id),   -- NULL = personal set
    owner_id        UUID REFERENCES users(id),   -- personal owner when team_id IS NULL
    name            TEXT NOT NULL,               -- e.g. 'Status', 'Priority', 'Stage', or a tag label
    data_type       property_data_type NOT NULL,
    is_tag          BOOLEAN NOT NULL DEFAULT FALSE,
    applies_to      entity_type,                 -- NULL = any entity type
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, owner_id, name)
);

CREATE TABLE property_options (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_definition_id  UUID REFERENCES property_definitions(id) ON DELETE CASCADE,
    label                   TEXT NOT NULL,
    color                   TEXT,
    sort_order              INT NOT NULL DEFAULT 0
);

-- single-value properties (text/number/date/boolean/user_ref)
CREATE TABLE entity_properties (
    entity_id               UUID REFERENCES entities(id) ON DELETE CASCADE,
    property_definition_id  UUID REFERENCES property_definitions(id) ON DELETE CASCADE,
    value_text              TEXT,
    value_number            NUMERIC,
    value_date              TIMESTAMPTZ,
    value_boolean           BOOLEAN,
    value_user_id           UUID REFERENCES users(id),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_id, property_definition_id)
);

-- multi-select / tags: many options per (entity, property)
CREATE TABLE entity_property_options (
    entity_id               UUID REFERENCES entities(id) ON DELETE CASCADE,
    property_definition_id  UUID REFERENCES property_definitions(id) ON DELETE CASCADE,
    option_id                UUID REFERENCES property_options(id) ON DELETE CASCADE,
    added_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_id, property_definition_id, option_id)
);

-- ============================================================
-- MENTIONS / BACKLINK GRAPH: the @mention primitive.
-- Bidirectional by construction (query in either direction).
-- ============================================================

CREATE TABLE mentions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    source_field    TEXT,               -- 'body', 'comment', 'agent_prompt', etc.
    target_entity_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    target_user_id  UUID REFERENCES users(id),  -- when the mention target is a person, not an entity
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mentions_source ON mentions(source_entity_id);
CREATE INDEX idx_mentions_target ON mentions(target_entity_id);

-- ============================================================
-- SEARCH: name/title index and content index kept distinct,
-- mirroring NameSearch vs ContentSearch being separate tools.
-- ============================================================

CREATE TABLE search_name_index (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    name_tsv        TSVECTOR NOT NULL
);

CREATE TABLE search_content_index (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    content_tsv     TSVECTOR NOT NULL
);

CREATE INDEX idx_search_name ON search_name_index USING GIN(name_tsv);
CREATE INDEX idx_search_content ON search_content_index USING GIN(content_tsv);

-- ============================================================
-- CHANNELS & MESSAGES
-- ============================================================

CREATE TYPE channel_type AS ENUM ('private', 'team', 'dm');

CREATE TABLE channels (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    channel_type    channel_type NOT NULL
);

CREATE TABLE channel_participants (
    channel_id      UUID REFERENCES channels(entity_id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member',  -- owner/admin/member
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at         TIMESTAMPTZ,
    PRIMARY KEY (channel_id, user_id)
);

CREATE TABLE channel_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id      UUID REFERENCES channels(entity_id) ON DELETE CASCADE,
    parent_message_id UUID REFERENCES channel_messages(id), -- thread reply self-ref
    sender_user_id  UUID REFERENCES users(id),
    sender_bot_id   UUID REFERENCES bots(id),               -- one of user/bot is set
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_channel_messages_channel_time ON channel_messages(channel_id, created_at DESC);
CREATE INDEX idx_channel_messages_parent ON channel_messages(parent_message_id);

-- ============================================================
-- AGENT CHATS (distinct from channels: role-tagged, tool-using)
-- ============================================================

CREATE TABLE chats (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    model           TEXT
);

CREATE TABLE chat_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id         UUID REFERENCES chats(entity_id) ON DELETE CASCADE,
    role            TEXT NOT NULL,          -- user/assistant/tool
    content         TEXT,
    tool_calls      JSONB,
    attachment_ids  UUID[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_messages_chat_time ON chat_messages(chat_id, created_at);

-- ============================================================
-- CALLS
-- ============================================================

CREATE TABLE calls (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    duration_seconds INT,
    recorded_at     TIMESTAMPTZ NOT NULL,
    shared_to_team  BOOLEAN NOT NULL DEFAULT TRUE  -- opt-out flag; false = personal memory only
);

CREATE TABLE call_transcript_segments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id         UUID REFERENCES calls(entity_id) ON DELETE CASCADE,
    speaker_user_id UUID REFERENCES users(id),
    start_ms        INT NOT NULL,
    end_ms          INT NOT NULL,
    text            TEXT NOT NULL
);

CREATE INDEX idx_call_segments_call ON call_transcript_segments(call_id, start_ms);

-- ============================================================
-- EMAIL (Gmail-shaped: label-driven state)
-- ============================================================

CREATE TABLE inboxes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    email_address   TEXT NOT NULL,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    is_delegated    BOOLEAN NOT NULL DEFAULT FALSE,
    delegated_by_user_id UUID REFERENCES users(id),
    provider        TEXT NOT NULL DEFAULT 'gmail'
);

CREATE TABLE email_threads (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    inbox_id        UUID REFERENCES inboxes(id),
    subject         TEXT
);

CREATE TABLE email_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id       UUID REFERENCES email_threads(entity_id) ON DELETE CASCADE,
    sender          TEXT NOT NULL,
    recipients      JSONB NOT NULL DEFAULT '[]',
    cc              JSONB NOT NULL DEFAULT '[]',
    bcc             JSONB NOT NULL DEFAULT '[]',
    body            TEXT,
    sent_at         TIMESTAMPTZ NOT NULL
);

CREATE TABLE email_labels (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id        UUID REFERENCES inboxes(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    is_system       BOOLEAN NOT NULL DEFAULT FALSE  -- INBOX/SENT/STARRED/... vs custom
);

CREATE TABLE email_message_labels (
    message_id      UUID REFERENCES email_messages(id) ON DELETE CASCADE,
    label_id        UUID REFERENCES email_labels(id) ON DELETE CASCADE,
    PRIMARY KEY (message_id, label_id)
);

CREATE TYPE sender_policy_type AS ENUM ('signal', 'noise', 'block');

CREATE TABLE sender_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id        UUID REFERENCES inboxes(id) ON DELETE CASCADE,
    sender_address  TEXT NOT NULL,
    policy          sender_policy_type NOT NULL,
    UNIQUE (inbox_id, sender_address)
);

-- ============================================================
-- CALENDAR
-- ============================================================

CREATE TABLE calendars (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id        UUID REFERENCES inboxes(id),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    is_writable     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE calendar_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    calendar_id     UUID REFERENCES calendars(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    start_at        TIMESTAMPTZ NOT NULL,
    end_at          TIMESTAMPTZ NOT NULL,
    attendees       JSONB NOT NULL DEFAULT '[]',
    recurrence_rule TEXT,        -- RRULE string; instances expanded at query time
    recurrence_scope_note TEXT   -- tracks 'this'/'following'/'all' edits per instance if needed
);

-- ============================================================
-- CRM
-- ============================================================

CREATE TABLE companies (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    domains         TEXT[] NOT NULL DEFAULT '{}',
    last_interaction_at TIMESTAMPTZ
    -- Stage / Owner / Revenue live in entity_properties, same as custom fields
);

CREATE TABLE contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_entity_id UUID REFERENCES companies(entity_id) ON DELETE CASCADE,
    name            TEXT,
    email           TEXT NOT NULL
);

-- ============================================================
-- BOTS (distinct from agent chats — programmatic actors)
-- ============================================================

CREATE TABLE bots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    handle          TEXT NOT NULL UNIQUE,
    owner_user_id   UUID REFERENCES users(id),
    owner_team_id   UUID REFERENCES teams(id),
    description     TEXT,
    avatar_url      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE bot_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id          UUID REFERENCES bots(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,   -- secret itself never stored/returned after mint
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ
);

CREATE TABLE bot_channel_access (
    bot_id          UUID REFERENCES bots(id) ON DELETE CASCADE,
    channel_id      UUID REFERENCES channels(entity_id) ON DELETE CASCADE,
    webhook_url     TEXT NOT NULL,
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,
    PRIMARY KEY (bot_id, channel_id)
);

-- ============================================================
-- REMINDERS & NOTIFICATIONS
-- ============================================================

CREATE TABLE reminders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    text            TEXT NOT NULL,
    remind_at       TIMESTAMPTZ NOT NULL,
    attached_entity_id UUID REFERENCES entities(id),  -- NULL = standalone
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_reminders_user_pending ON reminders(user_id, remind_at) WHERE completed_at IS NULL;

CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    notif_type      TEXT NOT NULL,
    entity_id       UUID REFERENCES entities(id),
    seen_at         TIMESTAMPTZ,
    done_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_notifications_user_unseen ON notifications(user_id) WHERE seen_at IS NULL;

-- ============================================================
-- IMPORT LEDGER (staged before becoming real entities)
-- ============================================================

CREATE TYPE import_status AS ENUM ('staged', 'in_flight', 'imported', 'declined');
CREATE TYPE import_source AS ENUM ('notion', 'linear', 'slack');

CREATE TABLE import_entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    source          import_source NOT NULL,
    external_id     TEXT NOT NULL,
    status          import_status NOT NULL DEFAULT 'staged',
    target_entity_id UUID REFERENCES entities(id),  -- set once imported
    imported_by_user_id UUID REFERENCES users(id),  -- may differ from user_id (teammate imported)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, external_id)
);

-- ============================================================
-- ACTIVITY LOG (includes agent-on-behalf-of-user actions)
-- ============================================================

CREATE TABLE activity_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) NOT NULL,   -- attributed-to user (even if agent acted)
    actor           TEXT NOT NULL DEFAULT 'user',          -- 'user' | 'agent'
    action_type     TEXT NOT NULL,                          -- e.g. 'property_change', 'send_email'
    entity_id       UUID REFERENCES entities(id),
    property_name   TEXT,
    property_type   property_data_type,
    from_value      JSONB,
    to_value        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_activity_user_time ON activity_log(user_id, created_at DESC);

-- ============================================================
-- SKILLS (just documents + a flag, per ListSkills' own description)
-- ============================================================

CREATE TABLE skill_flags (
    entity_id       UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE
    -- presence of a row = "this document is a skill"; no other columns needed
);

-- ============================================================
-- THIRD-PARTY TOOL SURFACE (SearchTools / LoadTools)
-- ============================================================

CREATE TABLE integrations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    team_id         UUID REFERENCES teams(id),
    provider        TEXT NOT NULL,           -- 'slack', 'gmail', 'linear', 'github', ...
    connected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    tool_manifest   JSONB NOT NULL DEFAULT '[]'  -- cached tool defs, searched by keyword at runtime
);
```

---

## 4. What this schema deliberately leaves out (GUI-only concerns)

- **Canvas** (2D board) — pure spatial/visual layer, no agent-native equivalent; skip it.
- **Window manager state / split panes** — client-side only.
- **"Signal vs Noise" inbox view** — that's a query/filter over `sender_policies` +
  `email_message_labels`, not a stored state.

## 5. Where a headless build should diverge from Macro

- **CRDTs for `documents.content_md`**: only worth it if you expect concurrent
  multi-agent or multi-user edits to the same doc. If it's single-agent-at-a-time,
  a plain `updated_at` + optimistic lock is simpler and Postgres-native.
- **`activity_log.actor`**: Macro's docs stress that agent actions are attributed
  to the user, not the agent, for permission purposes — but you may want an
  additional `agent_session_id` column if you need to debug/replay what a specific
  agent run did, since "attributed to user" alone loses that thread.
- **Bot vs agent-chat split**: Macro keeps these as two systems (bots = webhook-driven
  programmatic posters, chats = conversational agent sessions). If your headless
  version only needs one kind of actor, you can likely collapse `bots` into `chats`
  with a `chat_type` discriminator instead of maintaining both.

## 6. Latest MCP Stateless Conventions (adopted by this project)

This implementation targets the 2026-07-28 MCP spec (stateless core):

- Remove mandatory `initialize` + `notifications/initialized`. Every request carries `MCP-Protocol-Version` (header for HTTP + `_meta.io.modelcontextprotocol/protocolVersion`).
- No `Mcp-Session-Id`. Default to stateless (per-request factory for Streamable HTTP). Sessions only when you explicitly need server-to-client push or per-client isolation.
- Mandatory `server/discover` RPC: returns supported protocol versions, capabilities, serverInfo.
- Streamable HTTP requires `Mcp-Method` + `Mcp-Name` headers for routing/authorization without body parse.
- List results (`tools/list`, `resources/list`, ...) MUST include `ttlMs` + `cacheScope` (and SHOULD be deterministic order).
- All results carry `resultType: "complete" | "input_required"` (MRTR for elicitation/confirmations).
- WebSearch / WebFetch / code exec tools are implemented as thin facades or direct (Claude built-ins or local sandbox equivalents).
- Tool catalog is stable and versioned; clients can cache `tools/list`.

See README for run instructions and client config examples.

## 7. Tool Surface (67+ tools, Macro parity)

The MCP server exposes a tool surface modeled directly on Macro's registry (see fetched `docs.macro.com/AI/mcp/tools/*` and `llms.txt`).

Core groups (non-exhaustive; exact names + schemas in server code):

**Discovery & Meta**
- SelfKnowledge, server/discover, SearchTools, LoadTools

**Listing & Browsing**
- ListEntities, ListTags, ListSkills, ListBots, ListTeamMembers, ListInboxes, ListLabels, ListReminders, ListNotifications, ListCompanies, ListCalendarEvents, ListCalendars, ListImportEntities

**Read**
- ReadContent, ReadMetadata, ReadProject, ReadChat, ReadCallRecord, ReadChannelMessages, ReadChannelThread, ReadChannelMessageContext, GetThread, GetEntityProperties, GetCompany, GetBotWebhooks, ReadActivity

**Create / Edit / Delete**
- CreateDocument, EditDocument, RenameDocument, CreateProject, MoveToProject, CreateChannel, RenameChannel, ManageChannelParticipants, SendChannelMessage, CreateTag, EditTag, DeleteTag, CreateReminder, UpdateReminder, DeleteReminder, CreateCalendarEvent, UpdateCalendarEvent, DeleteCalendarEvent, CreateBot, ConfigureBot, DeleteBot, IssueBotCredential, ManageBotChannelAccess, CreateImportEntity, DeleteImportEntity, ImportNotionPage

**Properties & Bulk**
- SetEntityProperty, GetEntityProperties, BulkSetEntityPropertyOptions

**Search**
- NameSearch, ContentSearch, SearchSkills

**Email / Labels**
- UpdateThreadLabels, SetSenderPolicy, SendEmail

**Notifications**
- MarkNotificationsSeen, MarkNotificationsDone

**Agents & Misc**
- Subagent, DisplayResults, BashCodeExecution, TextEditorCodeExecution, WebSearch, WebFetch

(Plus any Macro additions such as full bot credential flows, activity, etc.)

Each tool's `input_schema` mirrors Macro's (from live MCP + docs). Handlers are implemented against the shared DDL/ORMs.

See the Python MCP server registry for the exact Pydantic/Zod schemas and docstrings.

---

Want the full per-tool input/output JSON Schemas + handler implementations, or the Drizzle/SQLAlchemy query patterns for the trickier ones (propf soup ASTs, FTS ranking, bulk option deltas)?
