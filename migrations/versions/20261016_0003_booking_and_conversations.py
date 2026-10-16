"""Схемы booking и conversations: записи, переписки, журнал ленты.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать схемы, таблицы и ограничения."""
    # btree_gist нужен, чтобы в одном GiST-ограничении сравнивать uuid (=) и интервалы (&&).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE SCHEMA IF NOT EXISTS booking")
    op.execute("CREATE SCHEMA IF NOT EXISTS conversations")
    _booking()
    _conversations()


def _booking() -> None:
    op.create_table(
        "appointments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("service_title", sa.Text(), nullable=False),
        sa.Column("service_duration_min", sa.Integer(), nullable=False),
        sa.Column("service_price_amount", sa.BigInteger(), nullable=True),
        sa.Column("client_display_name", sa.Text(), nullable=False),
        sa.Column("client_phone_masked", sa.Text(), nullable=False),
        sa.Column("client_visit_number", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("hold_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_deadline_hours", sa.Integer(), nullable=False),
        sa.Column("reschedule_of", sa.UUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(length=24), nullable=True),
        sa.Column("cancel_reason", sa.String(length=24), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('requested', 'confirmed', 'cancelled', 'completed')",
            name=op.f("ck_appointments_appointment_status"),
        ),
        sa.CheckConstraint(
            "cancelled_by IN ('client', 'master', 'system')", name=op.f("ck_appointments_cancelled_by")
        ),
        sa.CheckConstraint(
            "cancel_reason IN ('client_cancelled', 'declined', 'expired', 'rescheduled')",
            name=op.f("ck_appointments_cancel_reason"),
        ),
        postgresql.ExcludeConstraint(
            (sa.column("master_id"), "="),
            (sa.text("tstzrange(start_at, end_at)"), "&&"),
            where=sa.text("status IN ('requested', 'confirmed')"),
            using="gist",
            name="ex_appointments_no_overlap",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
        schema="booking",
        comment="Заявки и записи клиентов к мастерам",
    )
    op.create_index(
        "ix_appointments_master_start", "appointments", ["master_id", "start_at"], schema="booking"
    )
    op.create_index(
        "ix_appointments_client_master",
        "appointments",
        ["client_id", "master_id", "start_at"],
        schema="booking",
    )
    op.create_index(
        "ix_appointments_reschedule_of",
        "appointments",
        ["reschedule_of"],
        schema="booking",
        postgresql_where=sa.text("reschedule_of IS NOT NULL AND status = 'requested'"),
    )


def _conversations() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("last_event_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("master_id", "client_id", name="uq_conversations_master_client"),
        schema="conversations",
        comment="Переписки клиентов с мастерами",
    )
    op.create_index("ix_conversations_client", "conversations", ["client_id"], schema="conversations")
    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("client_message_id", sa.UUID(), nullable=True),
        sa.Column("appointment_id", sa.UUID(), nullable=True),
        sa.Column("ai_generated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        schema="conversations",
        comment="Сообщения переписок (содержимое по видам — jsonb)",
    )
    op.create_index(
        "ix_messages_conversation_id", "messages", ["conversation_id", "id"], schema="conversations"
    )
    op.create_index(
        "ux_messages_client_message_id",
        "messages",
        ["conversation_id", "client_message_id"],
        unique=True,
        schema="conversations",
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )
    op.create_index(
        "ux_messages_appointment_card",
        "messages",
        ["conversation_id", "appointment_id"],
        unique=True,
        schema="conversations",
        postgresql_where=sa.text("appointment_id IS NOT NULL"),
    )
    op.create_table(
        "feed_events",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("change", sa.Text(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.conversations.id"],
            name=op.f("fk_feed_events_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("conversation_id", "seq", name=op.f("pk_feed_events")),
        schema="conversations",
        comment="Журнал ленты для Last-Event-ID (сутки)",
    )
    op.create_index("ix_feed_events_created_at", "feed_events", ["created_at"], schema="conversations")


def downgrade() -> None:
    """Удалить схемы booking и conversations (расширение btree_gist остаётся)."""
    op.execute("DROP SCHEMA IF EXISTS conversations CASCADE")
    op.execute("DROP SCHEMA IF EXISTS booking CASCADE")
