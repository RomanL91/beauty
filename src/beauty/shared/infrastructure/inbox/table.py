"""Таблица ``infra.inbox``."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID

from beauty.shared.infrastructure.db.metadata import metadata

inbox_table = Table(
    "inbox",
    metadata,
    Column("consumer", Text, nullable=False),
    Column("message_id", UUID(as_uuid=True), nullable=False),
    Column("processed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("consumer", "message_id"),
    Index("ix_inbox_processed_at", "processed_at"),
    schema="infra",
    comment="Обработанные входящие сообщения (дедупликация at-least-once доставки)",
)
