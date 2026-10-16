"""Схема notifications: подписки устройств на Web Push; отметка о напоминании у записи.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать схему и таблицу; добавить ``reminded_at``."""
    op.execute("CREATE SCHEMA IF NOT EXISTS notifications")
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False, comment="учётная запись (identity)"),
        sa.Column("app", sa.Text(), nullable=False, comment="client | master"),
        sa.Column("master_id", sa.UUID(), nullable=False, comment="чья страница или чей кабинет"),
        sa.Column("endpoint", sa.Text(), nullable=False, comment="адрес push-сервиса устройства"),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_subscriptions_endpoint")),
        schema="notifications",
        comment="Устройства, подписанные на Web Push",
    )
    op.create_index(
        "ix_push_subscriptions_audience",
        "push_subscriptions",
        ["app", "master_id", "account_id"],
        schema="notifications",
    )
    op.add_column(
        "appointments",
        sa.Column("reminded_at", sa.DateTime(timezone=True), comment="когда клиенту напомнили о визите"),
        schema="booking",
    )


def downgrade() -> None:
    """Удалить схему notifications и ``reminded_at``."""
    op.drop_column("appointments", "reminded_at", schema="booking")
    op.execute("DROP SCHEMA IF EXISTS notifications CASCADE")
