"""Таблица ``infra.outbox``."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, Table, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from beauty.shared.infrastructure.db.metadata import metadata

OUTBOX_NOTIFY_CHANNEL = "beauty_outbox"
"""Канал ``LISTEN/NOTIFY``, в который триггер сигналит о новых записях."""

outbox_table = Table(
    "outbox",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, comment="id события = message_id в брокере"),
    Column("routing_key", Text, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("event_version", Integer, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("published_at", DateTime(timezone=True)),
    Index(
        "ix_outbox_unpublished",
        "id",
        postgresql_where=text("published_at IS NULL"),
    ),
    Index(
        "ix_outbox_published_at",
        "published_at",
        postgresql_where=text("published_at IS NOT NULL"),
    ),
    schema="infra",
    comment="Транзакционный outbox доменных событий",
)
