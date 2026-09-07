import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from agent_native_workspace.db import get_engine, get_sessionmaker
from agent_native_workspace.models import (
    Channel,
    ChannelMessage,
    Document,
    Entity,
    EntityProperty,
    EntityPropertyOption,
    EntityType,
    Mention,
    PropertyDataType,
    PropertyDefinition,
    PropertyOption,
    Reminder,
    User,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "users","teams","team_members","entities","documents",
    "property_definitions","property_options","entity_properties","entity_property_options",
    "mentions","bots","bot_credentials","channels","channel_participants",
    "bot_channel_access","channel_messages","chats","chat_messages","calls",
    "call_transcript_segments","inboxes","email_threads","email_messages","email_labels",
    "email_message_labels","sender_policies","calendars","calendar_events","companies",
    "contacts","reminders","notifications","import_entities","activity_log","skill_flags",
    "integrations","schema_migrations",
}


def uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def engine():
    return get_engine()


@pytest.fixture
def session(engine):
    Session = get_sessionmaker(engine)
    with Session() as s:
        yield s
        s.rollback()


def test_canonical_sql_exists():
    assert (ROOT / "schema" / "001_init.sql").is_file()


def test_catalog_tables(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%'"
            )
        ).fetchall()
    names = {r[0] for r in rows}
    missing = EXPECTED - names
    assert not missing, f"missing: {sorted(missing)}"


def test_property_definition_partial_unique(session):
    u = User(id=uid(), email=f"uniq-{uid()}@ex.com")
    session.add(u)
    session.flush()
    session.add(PropertyDefinition(id=uid(), owner_id=u.id, name="Status", data_type=PropertyDataType.select))
    session.flush()
    session.add(PropertyDefinition(id=uid(), owner_id=u.id, name="Status", data_type=PropertyDataType.select))
    with pytest.raises(IntegrityError):
        session.flush()


def test_document_as_task_properties_mentions_search(session, engine):
    u = User(id=uid(), email=f"task-{uid()}@ex.com", display_name="Ada")
    session.add(u)
    session.flush()
    doc_id = uid()
    session.add(Entity(id=doc_id, entity_type=EntityType.document, owner_id=u.id, name="Ship schema"))
    session.flush()
    session.add(Document(entity_id=doc_id, content_md="# Ship schema\n\nDo the migrate."))
    status = PropertyDefinition(id=uid(), owner_id=u.id, name=f"Status-{uid()[:8]}", data_type="select", applies_to="document")
    tags = PropertyDefinition(id=uid(), owner_id=u.id, name=f"Tags-{uid()[:8]}", data_type="multi_select", is_tag=1, applies_to="document")
    session.add_all([status, tags])
    session.flush()
    todo = PropertyOption(id=uid(), property_definition_id=status.id, label="Todo", color="gray")
    inbox = PropertyOption(id=uid(), property_definition_id=tags.id, label="inbox", color="blue")
    session.add_all([todo, inbox])
    session.flush()
    session.add(EntityProperty(entity_id=doc_id, property_definition_id=status.id, value_text="Todo"))
    session.add(EntityPropertyOption(entity_id=doc_id, property_definition_id=tags.id, option_id=inbox.id))
    proj = uid()
    session.add(Entity(id=proj, entity_type=EntityType.project, owner_id=u.id, name="Workspace"))
    session.flush()
    session.add(Mention(id=uid(), source_entity_id=doc_id, source_field="body", target_entity_id=proj))
    session.commit()
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO search_name_fts(entity_id, name) VALUES (:e, :n)"), {"e": doc_id, "n": "Ship schema"})
        conn.execute(text("INSERT INTO search_content_fts(entity_id, content) VALUES (:e, :c)"), {"e": doc_id, "c": "Do the migrate"})
        conn.commit()
        hits = conn.execute(text("SELECT entity_id FROM search_name_fts WHERE search_name_fts MATCH 'schema'")).fetchall()
    assert any(h[0] == doc_id for h in hits)
    assert session.get(Document, doc_id).content_md.startswith("# Ship schema")


def test_extension_type_enforced(session):
    u = User(id=uid(), email=f"ext-{uid()}@ex.com")
    session.add(u)
    session.flush()
    e = Entity(id=uid(), entity_type=EntityType.project, owner_id=u.id, name="Not a doc")
    session.add(e)
    session.flush()
    session.add(Document(entity_id=e.id, content_md="nope"))
    with pytest.raises(Exception):
        session.flush()


def test_reminder_is_entity_extension(session):
    u = User(id=uid(), email=f"rem-{uid()}@ex.com")
    session.add(u)
    session.flush()
    e = uid()
    session.add(Entity(id=e, entity_type=EntityType.reminder, owner_id=u.id, name="Ping"))
    session.flush()
    session.add(Reminder(entity_id=e, user_id=u.id, text="Ping", remind_at="2026-09-08T00:00:00Z"))
    session.commit()
    assert session.get(Reminder, e).text == "Ping"


def test_channel_message_user_sender(session):
    u = User(id=uid(), email=f"ch-{uid()}@ex.com")
    session.add(u)
    session.flush()
    e = uid()
    session.add(Entity(id=e, entity_type=EntityType.channel, owner_id=u.id, name="ops"))
    session.flush()
    session.add(Channel(entity_id=e, channel_type="team"))
    session.flush()
    mid = uid()
    session.add(ChannelMessage(id=mid, channel_id=e, sender_user_id=u.id, content="hello"))
    session.commit()
    assert session.get(ChannelMessage, mid).content == "hello"


def test_entity_property_requires_exactly_one_value(session):
    u = User(id=uid(), email=f"prop-{uid()}@ex.com")
    session.add(u)
    session.flush()
    e = uid()
    session.add(Entity(id=e, entity_type=EntityType.document, owner_id=u.id, name="x"))
    session.flush()
    session.add(Document(entity_id=e))
    p = PropertyDefinition(id=uid(), owner_id=u.id, name=f"P-{uid()[:8]}", data_type="text")
    session.add(p)
    session.flush()
    session.add(EntityProperty(entity_id=e, property_definition_id=p.id, value_text="high", value_boolean=1))
    with pytest.raises(IntegrityError):
        session.flush()
