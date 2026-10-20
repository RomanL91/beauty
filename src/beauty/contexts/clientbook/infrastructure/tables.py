"""Таблицы схемы ``clientbook``: карточки клиентов у мастеров и заметки."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Table, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from beauty.contexts.clientbook.domain.client_file import NoteAuthor
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import StringValueObjectType

SCHEMA = "clientbook"
NoteAuthorType = StringValueObjectType(NoteAuthor, lambda author: author.value)

files = Table(
    "files",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("master_id", UUID(as_uuid=True), nullable=False),
    Column("client_id", UUID(as_uuid=True), nullable=False),
    Column("name", Text, comment="имя клиента у мастера; NULL — подпись по телефону"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    UniqueConstraint("master_id", "client_id", name="uq_files_master_client"),
    schema=SCHEMA,
    comment="Карточки клиентов у мастеров (заводятся при первом имени или заметке)",
)

notes = Table(
    "notes",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("file_id", UUID(as_uuid=True), ForeignKey(files.c.id, ondelete="CASCADE"), nullable=False),
    Column("text", Text, nullable=False),
    Column("author", NoteAuthorType, nullable=False, comment="master | agent"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_notes_file_created", "file_id", "created_at"),
    schema=SCHEMA,
    comment="Заметки о клиентах: мастера и ИИ-администратора",
)
