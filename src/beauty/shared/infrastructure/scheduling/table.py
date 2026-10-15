"""Таблица ``infra.scheduled_jobs``."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, Table, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from beauty.shared.infrastructure.db.metadata import metadata


class JobStatus(StrEnum):
    """Состояния отложенной задачи."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


_STATUSES = ", ".join(f"'{status.value}'" for status in JobStatus)

scheduled_jobs_table = Table(
    "scheduled_jobs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("kind", Text, nullable=False),
    Column("dedup_key", Text, nullable=False, unique=True),
    Column("payload", JSONB, nullable=False),
    Column("due_at", DateTime(timezone=True), nullable=False),
    Column("status", Text, nullable=False, server_default=JobStatus.PENDING.value),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("locked_until", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(f"status IN ({_STATUSES})", name="status"),
    Index("ix_scheduled_jobs_due", "due_at", postgresql_where=text("status = 'pending'")),
    Index("ix_scheduled_jobs_lease", "locked_until", postgresql_where=text("status = 'running'")),
    Index(
        "ix_scheduled_jobs_dedup_prefix",
        "dedup_key",
        postgresql_ops={"dedup_key": "text_pattern_ops"},
        postgresql_where=text("status = 'pending'"),
    ),
    schema="infra",
    comment="Отложенные задачи: напоминания, таймауты подтверждений и процессов",
)
