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

from beauty.contexts.conversations.domain.broadcast import BroadcastOrigin, BroadcastStatus
from beauty.contexts.conversations.domain.content import Author
from beauty.contexts.conversations.domain.conversation import Handler, NeedsMaster
from beauty.contexts.conversations.infrastructure.serialization import dump_content, load_content
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import JsonValueObjectType, StringValueObjectType

ContentType = JsonValueObjectType(dump_content, load_content)
AuthorType = StringValueObjectType(Author, lambda author: author.value)
HandlerType = StringValueObjectType(Handler, lambda handler: handler.value)
NeedsMasterType = StringValueObjectType(NeedsMaster, lambda reason: reason.value)
BroadcastStatusType = StringValueObjectType(BroadcastStatus, lambda status: status.value)
BroadcastOriginType = StringValueObjectType(BroadcastOrigin, lambda origin: origin.value)

conversations = Table(
    "conversations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("master_id", UUID(as_uuid=True), nullable=False),
    Column("client_id", UUID(as_uuid=True), nullable=False),
    Column("client_display_name", Text, nullable=False),
    Column("client_phone_masked", Text, nullable=False),
    Column("handler", HandlerType, nullable=False),
    Column("needs_master", NeedsMasterType),
    Column("last_message_author", AuthorType),
    Column("last_message_preview", Text),
    Column("last_message_at", DateTime(timezone=True)),
    Column("unread", Integer, nullable=False),
    Column("completed_visits", Integer, nullable=False),
    Column("last_event_seq", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    UniqueConstraint("master_id", "client_id", name="uq_conversations_master_client"),
    Index("ix_conversations_client", "client_id"),
    Index("ix_conversations_master_recent", "master_id", "last_message_at"),
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

broadcasts = Table(
    "broadcasts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("master_id", UUID(as_uuid=True), nullable=False),
    Column("text", Text, nullable=False),
    Column("photo_key", Text, comment="фото в хранилище файлов (подписанные ссылки)"),
    Column("status", BroadcastStatusType, nullable=False, comment="draft | sending | sent"),
    Column("origin", BroadcastOriginType, nullable=False, comment="master | agent"),
    Column("recipients", Integer, nullable=False),
    Column("delivered", Integer, nullable=False),
    Column("cursor", UUID(as_uuid=True), comment="последняя переписка, получившая объявление"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    Index("ix_broadcasts_master_created", "master_id", "created_at"),
    schema="conversations",
    comment="Рассылки объявлений мастеров всем их клиентам",
)

broadcast_blocks = Table(
    "broadcast_blocks",
    metadata,
    Column("master_id", UUID(as_uuid=True), primary_key=True),
    Column("blocked_at", DateTime(timezone=True), nullable=False),
    schema="conversations",
    comment="Мастера, которым администрация запретила рассылки",
)
