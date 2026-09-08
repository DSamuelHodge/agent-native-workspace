-- Agent-Native Workspace — canonical libSQL/SQLite DDL
-- Derived from docs/agent_native_workspace_schema.md
-- Dialect notes vs Postgres source:
--   ENUM -> TEXT + CHECK
--   UUID defaults -> application-supplied TEXT UUIDs
--   tsvector/GIN -> FTS5 (name vs content kept separate)
--   arrays -> JSON TEXT
--   reminders = entities extension; property uniqueness NULL-safe
--   bots before channel_messages

PRAGMA foreign_keys = ON;

CREATE TABLE users (
    id              TEXT PRIMARY KEY NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE teams (
    id              TEXT PRIMARY KEY NOT NULL,
    name            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE team_members (
    team_id         TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner','admin','member')),
    invited_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    joined_at       TEXT,
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE entities (
    id                TEXT PRIMARY KEY NOT NULL,
    entity_type       TEXT NOT NULL CHECK (entity_type IN (
        'document','project','channel','chat','call','email_thread','company','reminder'
    )),
    team_id           TEXT REFERENCES teams(id),
    owner_id          TEXT NOT NULL REFERENCES users(id),
    name              TEXT,
    parent_project_id TEXT REFERENCES entities(id),
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at        TEXT
);

CREATE INDEX idx_entities_team_type ON entities(team_id, entity_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_entities_parent ON entities(parent_project_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_entities_owner ON entities(owner_id) WHERE deleted_at IS NULL;

CREATE TABLE documents (
    entity_id   TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    content_md  TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'native' CHECK (source IN (
        'native','uploaded_pdf','uploaded_docx','uploaded_xlsx','imported'
    )),
    is_editable INTEGER NOT NULL DEFAULT 1 CHECK (is_editable IN (0,1))
);

CREATE TRIGGER trg_documents_entity_type
BEFORE INSERT ON documents
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'documents.entity_id must be entity_type=document')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities e WHERE e.id = NEW.entity_id AND e.entity_type = 'document'
    );
END;

CREATE TABLE property_definitions (
    id          TEXT PRIMARY KEY NOT NULL,
    team_id     TEXT REFERENCES teams(id),
    owner_id    TEXT REFERENCES users(id),
    name        TEXT NOT NULL,
    data_type   TEXT NOT NULL CHECK (data_type IN (
        'text','number','date','boolean','select','multi_select','user_ref'
    )),
    is_tag      INTEGER NOT NULL DEFAULT 0 CHECK (is_tag IN (0,1)),
    applies_to  TEXT CHECK (applies_to IS NULL OR applies_to IN (
        'document','project','channel','chat','call','email_thread','company','reminder'
    )),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (team_id IS NOT NULL OR owner_id IS NOT NULL)
);

CREATE UNIQUE INDEX uq_property_defs_team_name
    ON property_definitions (team_id, name) WHERE team_id IS NOT NULL;
CREATE UNIQUE INDEX uq_property_defs_personal_name
    ON property_definitions (owner_id, name) WHERE team_id IS NULL;

CREATE TABLE property_options (
    id                      TEXT PRIMARY KEY NOT NULL,
    property_definition_id  TEXT NOT NULL REFERENCES property_definitions(id) ON DELETE CASCADE,
    label                   TEXT NOT NULL,
    color                   TEXT,
    sort_order              INTEGER NOT NULL DEFAULT 0,
    UNIQUE (property_definition_id, label)
);

CREATE TABLE entity_properties (
    entity_id               TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    property_definition_id  TEXT NOT NULL REFERENCES property_definitions(id) ON DELETE CASCADE,
    value_text              TEXT,
    value_number            REAL,
    value_date              TEXT,
    value_boolean           INTEGER CHECK (value_boolean IS NULL OR value_boolean IN (0,1)),
    value_user_id           TEXT REFERENCES users(id),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (entity_id, property_definition_id),
    CHECK (
        (value_text IS NOT NULL) +
        (value_number IS NOT NULL) +
        (value_date IS NOT NULL) +
        (value_boolean IS NOT NULL) +
        (value_user_id IS NOT NULL) = 1
    )
);

CREATE TABLE entity_property_options (
    entity_id               TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    property_definition_id  TEXT NOT NULL REFERENCES property_definitions(id) ON DELETE CASCADE,
    option_id               TEXT NOT NULL REFERENCES property_options(id) ON DELETE CASCADE,
    added_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (entity_id, property_definition_id, option_id)
);

CREATE TABLE mentions (
    id               TEXT PRIMARY KEY NOT NULL,
    source_entity_id TEXT REFERENCES entities(id) ON DELETE CASCADE,
    source_field     TEXT,
    target_entity_id TEXT REFERENCES entities(id) ON DELETE CASCADE,
    target_user_id   TEXT REFERENCES users(id),
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (target_entity_id IS NOT NULL OR target_user_id IS NOT NULL)
);

CREATE INDEX idx_mentions_source ON mentions(source_entity_id);
CREATE INDEX idx_mentions_target ON mentions(target_entity_id);

-- FTS5: NameSearch vs ContentSearch kept distinct (content= external content tables optional;
-- store entity_id + text and maintain via app or triggers on documents/entities).
CREATE VIRTUAL TABLE search_name_fts USING fts5(
    entity_id UNINDEXED,
    name,
    tokenize = 'porter'
);

CREATE VIRTUAL TABLE search_content_fts USING fts5(
    entity_id UNINDEXED,
    content,
    tokenize = 'porter'
);

CREATE TABLE bots (
    id              TEXT PRIMARY KEY NOT NULL,
    name            TEXT NOT NULL,
    handle          TEXT NOT NULL UNIQUE,
    owner_user_id   TEXT REFERENCES users(id),
    owner_team_id   TEXT REFERENCES teams(id),
    description     TEXT,
    avatar_url      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at      TEXT
);

CREATE TABLE bot_credentials (
    id              TEXT PRIMARY KEY NOT NULL,
    bot_id          TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    revoked_at      TEXT
);

CREATE TABLE channels (
    entity_id    TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL CHECK (channel_type IN ('private','team','dm'))
);

CREATE TRIGGER trg_channels_entity_type
BEFORE INSERT ON channels
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'channels.entity_id must be entity_type=channel')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities e WHERE e.id = NEW.entity_id AND e.entity_type = 'channel'
    );
END;

CREATE TABLE channel_participants (
    channel_id TEXT NOT NULL REFERENCES channels(entity_id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL DEFAULT 'member',
    joined_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    left_at    TEXT,
    PRIMARY KEY (channel_id, user_id)
);

CREATE TABLE bot_channel_access (
    bot_id      TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    channel_id  TEXT NOT NULL REFERENCES channels(entity_id) ON DELETE CASCADE,
    webhook_url TEXT NOT NULL,
    granted_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    revoked_at  TEXT,
    PRIMARY KEY (bot_id, channel_id)
);

CREATE TABLE channel_messages (
    id                TEXT PRIMARY KEY NOT NULL,
    channel_id        TEXT NOT NULL REFERENCES channels(entity_id) ON DELETE CASCADE,
    parent_message_id TEXT REFERENCES channel_messages(id),
    sender_user_id    TEXT REFERENCES users(id),
    sender_bot_id     TEXT REFERENCES bots(id),
    content           TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (
        (sender_user_id IS NOT NULL AND sender_bot_id IS NULL)
        OR (sender_user_id IS NULL AND sender_bot_id IS NOT NULL)
    )
);

CREATE INDEX idx_channel_messages_channel_time ON channel_messages(channel_id, created_at DESC);
CREATE INDEX idx_channel_messages_parent ON channel_messages(parent_message_id);

CREATE TABLE chats (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    model     TEXT
);

CREATE TRIGGER trg_chats_entity_type
BEFORE INSERT ON chats
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'chats.entity_id must be entity_type=chat')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities e WHERE e.id = NEW.entity_id AND e.entity_type = 'chat'
    );
END;

CREATE TABLE chat_messages (
    id             TEXT PRIMARY KEY NOT NULL,
    chat_id        TEXT NOT NULL REFERENCES chats(entity_id) ON DELETE CASCADE,
    role           TEXT NOT NULL,
    content        TEXT,
    tool_calls     TEXT,
    attachment_ids TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX idx_chat_messages_chat_time ON chat_messages(chat_id, created_at);

CREATE TABLE calls (
    entity_id        TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    duration_seconds INTEGER,
    recorded_at      TEXT NOT NULL,
    shared_to_team   INTEGER NOT NULL DEFAULT 1 CHECK (shared_to_team IN (0,1))
);

CREATE TRIGGER trg_calls_entity_type
BEFORE INSERT ON calls
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'calls.entity_id must be entity_type=call')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities e WHERE e.id = NEW.entity_id AND e.entity_type = 'call'
    );
END;

CREATE TABLE call_transcript_segments (
    id              TEXT PRIMARY KEY NOT NULL,
    call_id         TEXT NOT NULL REFERENCES calls(entity_id) ON DELETE CASCADE,
    speaker_user_id TEXT REFERENCES users(id),
    start_ms        INTEGER NOT NULL,
    end_ms          INTEGER NOT NULL,
    text            TEXT NOT NULL
);

CREATE INDEX idx_call_segments_call ON call_transcript_segments(call_id, start_ms);

CREATE TABLE inboxes (
    id                   TEXT PRIMARY KEY NOT NULL,
    user_id              TEXT REFERENCES users(id) ON DELETE CASCADE,
    email_address        TEXT NOT NULL,
    is_primary           INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    is_delegated         INTEGER NOT NULL DEFAULT 0 CHECK (is_delegated IN (0,1)),
    delegated_by_user_id TEXT REFERENCES users(id),
    provider             TEXT NOT NULL DEFAULT 'gmail'
);

CREATE TABLE email_threads (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    inbox_id  TEXT REFERENCES inboxes(id),
    subject   TEXT
);

CREATE TRIGGER trg_email_threads_entity_type
BEFORE INSERT ON email_threads
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'email_threads.entity_id must be entity_type=email_thread')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities e WHERE e.id = NEW.entity_id AND e.entity_type = 'email_thread'
    );
END;

CREATE TABLE email_messages (
    id         TEXT PRIMARY KEY NOT NULL,
    thread_id  TEXT REFERENCES email_threads(entity_id) ON DELETE CASCADE,
    sender     TEXT NOT NULL,
    recipients TEXT NOT NULL DEFAULT '[]',
    cc         TEXT NOT NULL DEFAULT '[]',
    bcc        TEXT NOT NULL DEFAULT '[]',
    body       TEXT,
    sent_at    TEXT NOT NULL
);

CREATE TABLE email_labels (
    id         TEXT PRIMARY KEY NOT NULL,
    inbox_id   TEXT REFERENCES inboxes(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    is_system  INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0,1))
);

CREATE TABLE email_message_labels (
    message_id TEXT NOT NULL REFERENCES email_messages(id) ON DELETE CASCADE,
    label_id   TEXT NOT NULL REFERENCES email_labels(id) ON DELETE CASCADE,
    PRIMARY KEY (message_id, label_id)
);

CREATE TABLE sender_policies (
    id             TEXT PRIMARY KEY NOT NULL,
    inbox_id       TEXT REFERENCES inboxes(id) ON DELETE CASCADE,
    sender_address TEXT NOT NULL,
    policy         TEXT NOT NULL CHECK (policy IN ('signal','noise','block')),
    UNIQUE (inbox_id, sender_address)
);

CREATE TABLE calendars (
    id          TEXT PRIMARY KEY NOT NULL,
    inbox_id    TEXT REFERENCES inboxes(id),
    user_id     TEXT REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT,
    is_primary  INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    is_writable INTEGER NOT NULL DEFAULT 1 CHECK (is_writable IN (0,1))
);

CREATE TABLE calendar_events (
    id                    TEXT PRIMARY KEY NOT NULL,
    calendar_id           TEXT REFERENCES calendars(id) ON DELETE CASCADE,
    title                 TEXT NOT NULL,
    start_at              TEXT NOT NULL,
    end_at                TEXT NOT NULL,
    attendees             TEXT NOT NULL DEFAULT '[]',
    recurrence_rule       TEXT,
    recurrence_scope_note TEXT
);

CREATE TABLE companies (
    entity_id           TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    domains             TEXT NOT NULL DEFAULT '[]',
    last_interaction_at TEXT
);

CREATE TRIGGER trg_companies_entity_type
BEFORE INSERT ON companies
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'companies.entity_id must be entity_type=company')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities e WHERE e.id = NEW.entity_id AND e.entity_type = 'company'
    );
END;

CREATE TABLE contacts (
    id                TEXT PRIMARY KEY NOT NULL,
    company_entity_id TEXT REFERENCES companies(entity_id) ON DELETE CASCADE,
    name              TEXT,
    email             TEXT NOT NULL
);

CREATE TABLE reminders (
    entity_id          TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    user_id            TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text               TEXT NOT NULL,
    remind_at          TEXT NOT NULL,
    attached_entity_id TEXT REFERENCES entities(id),
    completed_at       TEXT
);

CREATE TRIGGER trg_reminders_entity_type
BEFORE INSERT ON reminders
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'reminders.entity_id must be entity_type=reminder')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities e WHERE e.id = NEW.entity_id AND e.entity_type = 'reminder'
    );
END;

CREATE INDEX idx_reminders_user_pending ON reminders(user_id, remind_at) WHERE completed_at IS NULL;

CREATE TABLE notifications (
    id         TEXT PRIMARY KEY NOT NULL,
    user_id    TEXT REFERENCES users(id) ON DELETE CASCADE,
    notif_type TEXT NOT NULL,
    entity_id  TEXT REFERENCES entities(id) ON DELETE CASCADE,
    seen_at    TEXT,
    done_at    TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX idx_notifications_user_unseen ON notifications(user_id) WHERE seen_at IS NULL;

CREATE TABLE import_entities (
    id                  TEXT PRIMARY KEY NOT NULL,
    user_id             TEXT REFERENCES users(id) ON DELETE CASCADE,
    source              TEXT NOT NULL CHECK (source IN ('notion','linear','slack')),
    external_id         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'staged' CHECK (status IN ('staged','in_flight','imported','declined')),
    target_entity_id    TEXT REFERENCES entities(id) ON DELETE CASCADE,
    imported_by_user_id TEXT REFERENCES users(id),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source, external_id)
);

CREATE TABLE activity_log (
    id            TEXT PRIMARY KEY NOT NULL,
    user_id       TEXT NOT NULL REFERENCES users(id),
    actor         TEXT NOT NULL DEFAULT 'user',
    action_type   TEXT NOT NULL,
    entity_id     TEXT REFERENCES entities(id) ON DELETE CASCADE,
    property_name TEXT,
    property_type TEXT CHECK (property_type IS NULL OR property_type IN (
        'text','number','date','boolean','select','multi_select','user_ref'
    )),
    from_value    TEXT,
    to_value      TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX idx_activity_user_time ON activity_log(user_id, created_at DESC);

CREATE TABLE skill_flags (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TRIGGER trg_skill_flags_entity_type
BEFORE INSERT ON skill_flags
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'skill_flags.entity_id must be entity_type=document')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities e WHERE e.id = NEW.entity_id AND e.entity_type = 'document'
    );
END;

CREATE TABLE integrations (
    id            TEXT PRIMARY KEY NOT NULL,
    user_id       TEXT REFERENCES users(id),
    team_id       TEXT REFERENCES teams(id),
    provider      TEXT NOT NULL,
    connected_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    tool_manifest TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE schema_migrations (
    version    TEXT PRIMARY KEY NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

INSERT INTO schema_migrations (version) VALUES ('001_init');
