"""Таблицы схемы ``conversations``.

* ``conversations`` — по одной на пару «мастер, клиент», со счётчиком событий ленты;
* ``messages`` — сообщения; ``client_message_id`` уникален в переписке (повтор
  отправки), карточка заявки — одна на запись;
* ``feed_events`` — журнал ленты для досылки по ``Last-Event-ID`` (хранится сутки).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from beauty.contexts.conversations.domain.content import Author
from beauty.contexts.conversations.infrastructure.serialization import dump_content, load_content
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import JsonValueObjectType, StringValueObjectType

ContentType = JsonValueObjectType(dump_content, load_content)
AuthorType = StringValueObjectType(Author, lambda author: author.value)

conversations = Table(
    "conversations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("master_id", UUID(as_uuid=True), nullable=False),
    Column("client_id", UUID(as_uuid=True), nullable=False),
    Column("last_event_seq", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    UniqueConstraint("master_id", "client_id", name="uq_conversations_master_client"),
    Index("ix_conversations_client", "client_id"),
    schema="conversations",
    comment="Переписки клиентов с мастерами",
)

messages = Table(
    "messages",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "conversation_id",
        UUID(as_uuid=True),
        ForeignKey(conversations.c.id, ondelete="CASCADE"),
        nullable=False,
    ),
    Column("author", AuthorType, nullable=False),
    Column("kind", Text, nullable=False),
    Column("content", ContentType, nullable=False),
    Column("client_message_id", UUID(as_uuid=True)),
    Column("appointment_id", UUID(as_uuid=True)),
    Column("ai_generated", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    Index("ix_messages_conversation_id", "conversation_id", "id"),
    Index(
        "ux_messages_client_message_id",
        "conversation_id",
        "client_message_id",
        unique=True,
        postgresql_where=text("client_message_id IS NOT NULL"),
    ),
    Index(
        "ux_messages_appointment_card",
        "conversation_id",
        "appointment_id",
        unique=True,
        postgresql_where=text("appointment_id IS NOT NULL"),
    ),
    schema="conversations",
    comment="Сообщения переписок (содержимое по видам — jsonb)",
)

feed_events = Table(
    "feed_events",
    metadata,
    Column(
        "conversation_id",
        UUID(as_uuid=True),
        ForeignKey(conversations.c.id, ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("seq", Integer, primary_key=True),
    Column("change", Text, nullable=False),
    Column("message_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_feed_events_created_at", "created_at"),
    schema="conversations",
    comment="Журнал ленты для Last-Event-ID (сутки)",
)
