from __future__ import annotations

import enum
from typing import Optional

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


class Base(DeclarativeBase):
    pass


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
    display_name: Mapped[Optional[str]] = mapped_column(Text)
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
    team_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("teams.id"))
    owner_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(Text)
    parent_project_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("entities.id"))
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    updated_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    deleted_at: Mapped[Optional[str]] = mapped_column(Text)

    document: Mapped[Optional["Document"]] = relationship(back_populates="entity")
    channel: Mapped[Optional["Channel"]] = relationship(back_populates="entity")
    reminder: Mapped[Optional["Reminder"]] = relationship(
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
    team_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("teams.id"))
    owner_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_tag: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    applies_to: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class PropertyOption(Base):
    __tablename__ = "property_options"
    __table_args__ = (UniqueConstraint("property_definition_id", "label"),)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    property_definition_id: Mapped[str] = mapped_column(Text, ForeignKey("property_definitions.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class EntityProperty(Base):
    __tablename__ = "entity_properties"
    __table_args__ = (PrimaryKeyConstraint("entity_id", "property_definition_id"),)
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"))
    property_definition_id: Mapped[str] = mapped_column(Text, ForeignKey("property_definitions.id", ondelete="CASCADE"))
    value_text: Mapped[Optional[str]] = mapped_column(Text)
    value_number: Mapped[Optional[float]] = mapped_column(Float)
    value_date: Mapped[Optional[str]] = mapped_column(Text)
    value_boolean: Mapped[Optional[int]] = mapped_column(Integer)
    value_user_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("users.id"))
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
    source_entity_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"))
    source_field: Mapped[Optional[str]] = mapped_column(Text)
    target_entity_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"))
    target_user_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("users.id"))
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
    parent_message_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("channel_messages.id"))
    sender_user_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("users.id"))
    sender_bot_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("bots.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))


class Bot(Base):
    __tablename__ = "bots"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    handle: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    owner_user_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("users.id"))
    owner_team_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("teams.id"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"))
    deleted_at: Mapped[Optional[str]] = mapped_column(Text)


class Reminder(Base):
    __tablename__ = "reminders"
    entity_id: Mapped[str] = mapped_column(Text, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    remind_at: Mapped[str] = mapped_column(Text, nullable=False)
    attached_entity_id: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("entities.id"))
    completed_at: Mapped[Optional[str]] = mapped_column(Text)
    entity: Mapped[Entity] = relationship(back_populates="reminder", foreign_keys=[entity_id])
