"""Таблицы схемы ``agent``."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, Table, Text
from sqlalchemy.dialects.postgresql import UUID

from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.shared.domain.secrets import HashedSecret
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import StringValueObjectType

TokenDigestType = StringValueObjectType(HashedSecret, lambda secret: secret.digest)
FaceType = StringValueObjectType(AgentFace, lambda face: face.value)

profiles = Table(
    "profiles",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, comment="id мастера"),
    Column("profile_name", Text, nullable=False, unique=True),
    Column("runs_api_key", Text, nullable=False, comment="ключ Runs API профиля Hermes"),
    Column("mcp_token", TokenDigestType, nullable=False, unique=True, comment="SHA-256 MCP-токена профиля"),
    Column("enabled", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    schema="agent",
    comment="ИИ-администраторы мастеров (профили Hermes)",
)

tickets = Table(
    "tickets",
    metadata,
    Column("id", Text, primary_key=True),
    Column("master_id", UUID(as_uuid=True), nullable=False),
    Column("face", FaceType, nullable=False),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column("client_id", UUID(as_uuid=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("handed_off", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    schema="agent",
    comment="Тикеты ходов агента (права одного хода)",
)
