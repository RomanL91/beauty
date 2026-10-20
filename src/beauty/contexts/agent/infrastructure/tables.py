"""Таблицы схемы ``agent``."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import UUID

from beauty.contexts.agent.domain.office import OfficeAuthor
from beauty.contexts.agent.domain.playbook import PracticeAuthor
from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.contexts.agent.infrastructure.serialization import dump_office, load_office
from beauty.shared.domain.secrets import HashedSecret
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import JsonValueObjectType, StringValueObjectType

TokenDigestType = StringValueObjectType(HashedSecret, lambda secret: secret.digest)
FaceType = StringValueObjectType(AgentFace, lambda face: face.value)
OfficeAuthorType = StringValueObjectType(OfficeAuthor, lambda author: author.value)
OfficeContentType = JsonValueObjectType(dump_office, load_office)
PracticeAuthorType = StringValueObjectType(PracticeAuthor, lambda author: author.value)

profiles = Table(
    "profiles",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, comment="id мастера"),
    Column("profile_name", Text, nullable=False, unique=True),
    Column("runs_api_key", Text, nullable=False, comment="ключ Runs API профиля Hermes"),
    Column("mcp_token", TokenDigestType, nullable=False, unique=True, comment="SHA-256 MCP-токена профиля"),
    Column("office_profile_name", Text, unique=True, comment="профиль кабинета (поручения мастера)"),
    Column("office_runs_api_key", Text),
    Column("office_mcp_token", TokenDigestType, unique=True, comment="SHA-256 MCP-токена кабинета"),
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
    Column("conversation_id", UUID(as_uuid=True), comment="ресепшн: переписка хода"),
    Column("client_id", UUID(as_uuid=True), comment="ресепшн: клиент хода"),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("handed_off", Boolean, nullable=False),
    Column("asked_master", Boolean, nullable=False, server_default=text("false")),
    Column("catalog", Text, comment="отпечаток страницы мастера в инструкциях хода"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    schema="agent",
    comment="Тикеты ходов агента (права одного хода)",
)

office_messages = Table(
    "office_messages",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("master_id", UUID(as_uuid=True), nullable=False),
    Column("author", OfficeAuthorType, nullable=False),
    Column("kind", Text, nullable=False),
    Column("content", OfficeContentType, nullable=False),
    Column("client_message_id", UUID(as_uuid=True)),
    Column("ai_generated", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    Index("ix_office_messages_master", "master_id", "id"),
    Index(
        "ux_office_messages_client_message_id",
        "master_id",
        "client_message_id",
        unique=True,
        postgresql_where=text("client_message_id IS NOT NULL"),
    ),
    schema="agent",
    comment="Лента поручений мастера его ИИ-администратору",
)

runs = Table(
    "runs",
    metadata,
    Column("id", Text, primary_key=True, comment="id тикета хода"),
    Column("master_id", UUID(as_uuid=True), nullable=False),
    Column("face", FaceType, nullable=False),
    Column("conversation_id", UUID(as_uuid=True)),
    Column("status", Text, nullable=False, comment="completed или статус сбоя"),
    Column("seconds", Float, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_runs_created_at", "created_at"),
    schema="agent",
    comment="Журнал ходов агента (итог и длительность)",
)

playbooks = Table(
    "playbooks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, comment="id мастера"),
    Column("auto_confirm", Boolean, nullable=False, comment="агент сам подтверждает записи клиентов"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    schema="agent",
    comment="Опыт мастера для его ИИ-администратора",
)

practices = Table(
    "practices",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("playbook_id", UUID(as_uuid=True), ForeignKey(playbooks.c.id, ondelete="CASCADE"), nullable=False),
    Column("service_id", UUID(as_uuid=True), comment="услуга мастера; NULL — общая запись"),
    Column("text", Text, nullable=False),
    Column("author", PracticeAuthorType, nullable=False, comment="master | agent"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_practices_playbook_created", "playbook_id", "created_at"),
    schema="agent",
    comment="Записи опыта мастера: общие и к услугам",
)
