"""Таблицы схемы ``notifications``."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, Table, Text
from sqlalchemy.dialects.postgresql import UUID

from beauty.contexts.notifications.domain.subscription import PushApp
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import StringValueObjectType

PushAppType = StringValueObjectType(PushApp, lambda app: app.value)

push_subscriptions = Table(
    "push_subscriptions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("account_id", UUID(as_uuid=True), nullable=False, comment="учётная запись (identity)"),
    Column("app", PushAppType, nullable=False, comment="client | master"),
    Column("master_id", UUID(as_uuid=True), nullable=False, comment="чья страница или чей кабинет"),
    Column("endpoint", Text, nullable=False, unique=True, comment="адрес push-сервиса устройства"),
    Column("p256dh", Text, nullable=False),
    Column("auth", Text, nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    Index("ix_push_subscriptions_audience", "app", "master_id", "account_id"),
    schema="notifications",
    comment="Устройства, подписанные на Web Push",
)
