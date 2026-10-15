"""Схемы infra и identity: outbox, inbox, отложенные задачи, вход через Telegram.

Revision ID: 0001
Revises:
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTBOX_NOTIFY_FUNCTION = """
CREATE OR REPLACE FUNCTION infra.notify_outbox() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('beauty_outbox', '');
    RETURN NULL;
END;
$$;
"""

OUTBOX_NOTIFY_TRIGGER = """
CREATE TRIGGER trg_outbox_notify
AFTER INSERT ON infra.outbox
FOR EACH STATEMENT EXECUTE FUNCTION infra.notify_outbox();
"""


def upgrade() -> None:
    """Создать схемы, таблицы, индексы и триггер уведомления relay."""
    op.execute("CREATE SCHEMA IF NOT EXISTS infra")
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    _create_infra()
    _create_identity()


def downgrade() -> None:
    """Удалить объекты миграции."""
    op.drop_table("client_sessions", schema="identity")
    op.drop_table("auth_challenges", schema="identity")
    op.drop_table("client_accounts", schema="identity")
    op.execute("DROP TRIGGER IF EXISTS trg_outbox_notify ON infra.outbox")
    op.execute("DROP FUNCTION IF EXISTS infra.notify_outbox()")
    op.drop_table("scheduled_jobs", schema="infra")
    op.drop_table("outbox", schema="infra")
    op.drop_table("inbox", schema="infra")
    op.execute("DROP SCHEMA IF EXISTS identity")


def _create_infra() -> None:
    """Outbox, inbox и отложенные задачи."""
    op.create_table(
        "outbox",
        sa.Column("id", sa.UUID(), nullable=False, comment="id события = message_id в брокере"),
        sa.Column("routing_key", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
        schema="infra",
        comment="Транзакционный outbox доменных событий",
    )
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["id"],
        schema="infra",
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "ix_outbox_published_at",
        "outbox",
        ["published_at"],
        schema="infra",
        postgresql_where=sa.text("published_at IS NOT NULL"),
    )
    op.execute(OUTBOX_NOTIFY_FUNCTION)
    op.execute(OUTBOX_NOTIFY_TRIGGER)

    op.create_table(
        "inbox",
        sa.Column("consumer", sa.Text(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("consumer", "message_id", name=op.f("pk_inbox")),
        schema="infra",
        comment="Обработанные входящие сообщения (дедупликация at-least-once доставки)",
    )
    op.create_index("ix_inbox_processed_at", "inbox", ["processed_at"], schema="infra")

    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("dedup_key", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed', 'cancelled')",
            name=op.f("ck_scheduled_jobs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_jobs")),
        sa.UniqueConstraint("dedup_key", name=op.f("uq_scheduled_jobs_dedup_key")),
        schema="infra",
        comment="Отложенные задачи: напоминания, таймауты подтверждений и процессов",
    )
    op.create_index(
        "ix_scheduled_jobs_due",
        "scheduled_jobs",
        ["due_at"],
        schema="infra",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_scheduled_jobs_lease",
        "scheduled_jobs",
        ["locked_until"],
        schema="infra",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "ix_scheduled_jobs_dedup_prefix",
        "scheduled_jobs",
        ["dedup_key"],
        schema="infra",
        postgresql_ops={"dedup_key": "text_pattern_ops"},
        postgresql_where=sa.text("status = 'pending'"),
    )


def _create_identity() -> None:
    """Учётные записи, попытки входа, сессии."""
    op.create_table(
        "client_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_accounts")),
        sa.UniqueConstraint("phone", name=op.f("uq_client_accounts_phone")),
        sa.UniqueConstraint("telegram_user_id", name=op.f("uq_client_accounts_telegram_user_id")),
        schema="identity",
        comment="Глобальные учётные записи клиентов",
    )

    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("browser_secret_digest", sa.Text(), nullable=False),
        sa.Column("confirmation_code", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'confirmed', 'completed', 'consumed', 'rejected', 'expired')",
            name=op.f("ck_auth_challenges_challenge_status"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["identity.client_accounts.id"],
            name=op.f("fk_auth_challenges_account_id_client_accounts"),
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_challenges")),
        sa.UniqueConstraint("nonce", name=op.f("uq_auth_challenges_nonce")),
        schema="identity",
        comment="Попытки входа через Telegram",
    )
    op.create_index(
        "ix_auth_challenges_awaiting_contact",
        "auth_challenges",
        ["telegram_user_id", sa.literal_column("created_at DESC")],
        schema="identity",
        postgresql_where=sa.text("status = 'confirmed'"),
    )
    op.create_index(
        "ix_auth_challenges_expiry",
        "auth_challenges",
        ["expires_at"],
        schema="identity",
        postgresql_where=sa.text("status IN ('pending', 'claimed', 'confirmed')"),
    )
    op.create_index(
        "ix_auth_challenges_account_id",
        "auth_challenges",
        ["account_id"],
        schema="identity",
        postgresql_where=sa.text("account_id IS NOT NULL"),
    )

    op.create_table(
        "client_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("refresh_digest", sa.Text(), nullable=False),
        sa.Column("previous_refresh_digest", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["identity.client_accounts.id"],
            name=op.f("fk_client_sessions_account_id_client_accounts"),
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_sessions")),
        schema="identity",
        comment="Сессии клиентов (refresh-токены хранятся хешами)",
    )
    op.create_index(
        "ix_client_sessions_active_by_account",
        "client_sessions",
        ["account_id"],
        schema="identity",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
