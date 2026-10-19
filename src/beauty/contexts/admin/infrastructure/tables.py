"""Таблицы схемы ``admin``: администраторы, сессии, журнал действий."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Table, Text
from sqlalchemy.dialects.postgresql import UUID

from beauty.shared.domain.secrets import HashedSecret
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import StringValueObjectType

SCHEMA = "admin"
SecretType = StringValueObjectType(HashedSecret, lambda secret: secret.digest)

administrators = Table(
    "administrators",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("login", Text, nullable=False, unique=True),
    Column("display_name", Text, nullable=False),
    Column("password_hash", Text, nullable=False, comment="scrypt$n$r$p$соль$ключ"),
    Column("active", Boolean, nullable=False),
    Column("failed_attempts", Integer, nullable=False),
    Column("locked_until", DateTime(timezone=True)),
    Column("last_login_at", DateTime(timezone=True)),
    Column("password_changed_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    schema=SCHEMA,
    comment="Администраторы панели хозяина сервиса",
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("admin_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.administrators.id"), nullable=False),
    Column("secret", SecretType, nullable=False, comment="SHA-256 секрета из cookie"),
    Column("csrf_token", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    Index("ix_admin_sessions_admin", "admin_id"),
    schema=SCHEMA,
    comment="Сессии администраторов (cookie bk_admin)",
)

audit = Table(
    "audit",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, comment="UUIDv7: порядок — по времени"),
    Column("admin_id", UUID(as_uuid=True), nullable=False),
    Column("admin_login", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("target", Text),
    Column("summary", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    schema=SCHEMA,
    comment="Журнал действий администраторов",
)
