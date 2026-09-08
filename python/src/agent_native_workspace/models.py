from __future__ import annotations

import enum

try:
    from sqlalchemy import (
        CheckConstraint,
        Float,
        ForeignKey,
        Integer,
        PrimaryKeyConstraint,
        Text,
        UniqueConstraint,
        text,
    )
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
    HAS_SQLA = True
except Exception:  # catalog / pure introspection path  # noqa: BLE001
    CheckConstraint = Float = ForeignKey = Integer = PrimaryKeyConstraint = Text = UniqueConstraint = text = None  # type: ignore
    DeclarativeBase = Mapped = mapped_column = relationship = None  # type: ignore
    HAS_SQLA = False

class Base:  # type: ignore
    if HAS_SQLA:
        # real base injected below when SQLA present
        pass
    __tablename__ = "_base_placeholder"

if HAS_SQLA:
    class _RealBase(DeclarativeBase):  # type: ignore
        pass
    Base = _RealBase  # type: ignore


class EntityType(enum.StrEnum):
    document = "document"
    project = "project"
    channel = "channel"
    chat = "chat"
    call = "call"
    email_thread = "email_thread"
    company = "company"
    reminder = "reminder"


class PropertyDataType(enum.StrEnum):
    text = "text"
    number = "number"
    date = "date"
    boolean = "boolean"
    select = "select"
    multi_select = "multi_select"
    user_ref = "user_ref"


class ChannelType(enum.StrEnum):
    private = "private"
    team = "team"
    dm = "dm"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    team_id: Mapped[str | None] = mapped_column(Text, ForeignKey("teams.id"))
    owner_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    parent_project_id: Mapped[str | None] = mapped_column(Text, ForeignKey("entities.id"))
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    updated_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    deleted_at: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document | None] = relationship(back_populates="entity")
    channel: Mapped[Channel | None] = relationship(back_populates="entity")
    reminder: Mapped[Reminder | None] = relationship(
        back_populates="entity", foreign_keys="Reminder.entity_id"
    )


class Document(Base):
    __tablename__ = "documents"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="native")
    is_editable: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    entity: Mapped[Entity] = relationship(back_populates="document")


class PropertyDefinition(Base):
    __tablename__ = "property_definitions"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    team_id: Mapped[str | None] = mapped_column(Text, ForeignKey("teams.id"))
    owner_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_tag: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    applies_to: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class PropertyOption(Base):
    __tablename__ = "property_options"
    __table_args__ = (UniqueConstraint("property_definition_id", "label"),)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    property_definition_id: Mapped[str] = mapped_column(Text, ForeignKey("property_definitions.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class EntityProperty(Base):
    __tablename__ = "entity_properties"
    __table_args__ = (PrimaryKeyConstraint("entity_id", "property_definition_id"),)
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"))
    property_definition_id: Mapped[str] = mapped_column(Text, ForeignKey("property_definitions.id", ondelete="CASCADE"))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[float | None] = mapped_column(Float)
    value_date: Mapped[str | None] = mapped_column(Text)
    value_boolean: Mapped[int | None] = mapped_column(Integer)
    value_user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    updated_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class EntityPropertyOption(Base):
    __tablename__ = "entity_property_options"
    __table_args__ = (PrimaryKeyConstraint("entity_id", "property_definition_id", "option_id"),)
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"))
    property_definition_id: Mapped[str] = mapped_column(Text, ForeignKey("property_definitions.id", ondelete="CASCADE"))
    option_id: Mapped[str] = mapped_column(Text, ForeignKey("property_options.id", ondelete="CASCADE"))
    added_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class Mention(Base):
    __tablename__ = "mentions"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_entity_id: Mapped[str | None] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"))
    source_field: Mapped[str | None] = mapped_column(Text)
    target_entity_id: Mapped[str | None] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"))
    target_user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class Channel(Base):
    __tablename__ = "channels"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    channel_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[Entity] = relationship(back_populates="channel")


class ChannelMessage(Base):
    __tablename__ = "channel_messages"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    channel_id: Mapped[str] = mapped_column(Text, ForeignKey("channels.entity_id", ondelete="CASCADE"))
    parent_message_id: Mapped[str | None] = mapped_column(Text, ForeignKey("channel_messages.id"))
    sender_user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    sender_bot_id: Mapped[str | None] = mapped_column(Text, ForeignKey("bots.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class Bot(Base):
    __tablename__ = "bots"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    handle: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    owner_team_id: Mapped[str | None] = mapped_column(Text, ForeignKey("teams.id"))
    description: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    deleted_at: Mapped[str | None] = mapped_column(Text)


class Reminder(Base):
    __tablename__ = "reminders"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    remind_at: Mapped[str] = mapped_column(Text, nullable=False)
    attached_entity_id: Mapped[str | None] = mapped_column(Text, ForeignKey("entities.id"))
    completed_at: Mapped[str | None] = mapped_column(Text)
    entity: Mapped[Entity] = relationship(back_populates="reminder", foreign_keys=[entity_id])


# ============================================================
# Additional tables (channels participants, chats, calls, email,
# calendars, CRM, activity, notifications, imports, bots, integrations)
# ============================================================

class ChannelParticipant(Base):
    __tablename__ = "channel_participants"
    __table_args__ = (PrimaryKeyConstraint("channel_id", "user_id"),)
    channel_id: Mapped[str] = mapped_column(Text, ForeignKey("channels.entity_id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text, server_default=text("'member'"))
    joined_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    left_at: Mapped[str | None] = mapped_column(Text)


class BotCredential(Base):
    __tablename__ = "bot_credentials"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    bot_id: Mapped[str] = mapped_column(Text, ForeignKey("bots.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    revoked_at: Mapped[str | None] = mapped_column(Text)


class BotChannelAccess(Base):
    __tablename__ = "bot_channel_access"
    __table_args__ = (PrimaryKeyConstraint("bot_id", "channel_id"),)
    bot_id: Mapped[str] = mapped_column(Text, ForeignKey("bots.id", ondelete="CASCADE"))
    channel_id: Mapped[str] = mapped_column(Text, ForeignKey("channels.entity_id", ondelete="CASCADE"))
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    revoked_at: Mapped[str | None] = mapped_column(Text)


class Chat(Base):
    __tablename__ = "chats"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    model: Mapped[str | None] = mapped_column(Text)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, ForeignKey("chats.entity_id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[str | None] = mapped_column(Text)  # JSON text
    attachment_ids: Mapped[str | None] = mapped_column(Text)  # JSON array text
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class Call(Base):
    __tablename__ = "calls"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recorded_at: Mapped[str] = mapped_column(Text, nullable=False)
    shared_to_team: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class CallTranscriptSegment(Base):
    __tablename__ = "call_transcript_segments"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    call_id: Mapped[str] = mapped_column(Text, ForeignKey("calls.entity_id", ondelete="CASCADE"))
    speaker_user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class Inbox(Base):
    __tablename__ = "inboxes"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    email_address: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_delegated: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    delegated_by_user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(Text, server_default=text("'gmail'"))


class EmailThread(Base):
    __tablename__ = "email_threads"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    inbox_id: Mapped[str | None] = mapped_column(Text, ForeignKey("inboxes.id"))
    subject: Mapped[str | None] = mapped_column(Text)


class EmailMessage(Base):
    __tablename__ = "email_messages"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    thread_id: Mapped[str] = mapped_column(Text, ForeignKey("email_threads.entity_id", ondelete="CASCADE"))
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    recipients: Mapped[str] = mapped_column(Text, server_default=text("'[]'"))
    cc: Mapped[str] = mapped_column(Text, server_default=text("'[]'"))
    bcc: Mapped[str] = mapped_column(Text, server_default=text("'[]'"))
    body: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[str] = mapped_column(Text, nullable=False)


class EmailLabel(Base):
    __tablename__ = "email_labels"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    inbox_id: Mapped[str] = mapped_column(Text, ForeignKey("inboxes.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class EmailMessageLabel(Base):
    __tablename__ = "email_message_labels"
    __table_args__ = (PrimaryKeyConstraint("message_id", "label_id"),)
    message_id: Mapped[str] = mapped_column(Text, ForeignKey("email_messages.id", ondelete="CASCADE"))
    label_id: Mapped[str] = mapped_column(Text, ForeignKey("email_labels.id", ondelete="CASCADE"))


class SenderPolicy(Base):
    __tablename__ = "sender_policies"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    inbox_id: Mapped[str] = mapped_column(Text, ForeignKey("inboxes.id", ondelete="CASCADE"))
    sender_address: Mapped[str] = mapped_column(Text, nullable=False)
    policy: Mapped[str] = mapped_column(Text, nullable=False)  # signal/noise/block


class Calendar(Base):
    __tablename__ = "calendars"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    inbox_id: Mapped[str | None] = mapped_column(Text, ForeignKey("inboxes.id"))
    user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_writable: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    calendar_id: Mapped[str] = mapped_column(Text, ForeignKey("calendars.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    start_at: Mapped[str] = mapped_column(Text, nullable=False)
    end_at: Mapped[str] = mapped_column(Text, nullable=False)
    attendees: Mapped[str] = mapped_column(Text, server_default=text("'[]'"))
    recurrence_rule: Mapped[str | None] = mapped_column(Text)
    recurrence_scope_note: Mapped[str | None] = mapped_column(Text)


class Company(Base):
    __tablename__ = "companies"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    domains: Mapped[str] = mapped_column(Text, server_default=text("'[]'"))
    last_interaction_at: Mapped[str | None] = mapped_column(Text)


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    company_entity_id: Mapped[str | None] = mapped_column(Text, ForeignKey("companies.entity_id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    notif_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text, ForeignKey("entities.id"))
    seen_at: Mapped[str | None] = mapped_column(Text)
    done_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class ImportEntity(Base):
    __tablename__ = "import_entities"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(Text, nullable=False)  # notion/linear/slack
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default=text("'staged'"))
    target_entity_id: Mapped[str | None] = mapped_column(Text, ForeignKey("entities.id"))
    imported_by_user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
    actor: Mapped[str] = mapped_column(Text, server_default=text("'user'"))
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text, ForeignKey("entities.id"))
    property_name: Mapped[str | None] = mapped_column(Text)
    property_type: Mapped[str | None] = mapped_column(Text)
    from_value: Mapped[str | None] = mapped_column(Text)
    to_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class SkillFlag(Base):
    __tablename__ = "skill_flags"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)


class Integration(Base):
    __tablename__ = "integrations"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    team_id: Mapped[str | None] = mapped_column(Text, ForeignKey("teams.id"))
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    connected_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    tool_manifest: Mapped[str] = mapped_column(Text, server_default=text("'[]'"))


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"
    version: Mapped[str] = mapped_column(Text, primary_key=True)
    applied_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
