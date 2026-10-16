"""Кабинет мастера: владелец страницы, сводка переписки для списка чатов.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Обязательные колонки сводки: значение для уже существующих переписок, затем без default.
_SUMMARY_REQUIRED = (
    ("client_display_name", sa.Text(), sa.text("'Клиент'")),
    ("client_phone_masked", sa.Text(), sa.text("''")),
    ("handler", sa.Text(), sa.text("'agent'")),
    ("unread", sa.Integer(), sa.text("0")),
    ("completed_visits", sa.Integer(), sa.text("0")),
)


def upgrade() -> None:
    """Добавить колонки и индексы."""
    op.add_column(
        "masters",
        sa.Column(
            "owner_phone",
            sa.Text(),
            nullable=True,
            comment="телефон учётной записи владельца (E.164) — вход в кабинет",
        ),
        schema="tenancy",
    )
    op.create_index(
        "ux_masters_owner_phone",
        "masters",
        ["owner_phone"],
        unique=True,
        schema="tenancy",
        postgresql_where=sa.text("owner_phone IS NOT NULL"),
    )
    for name, type_, default in _SUMMARY_REQUIRED:
        op.add_column(
            "conversations",
            sa.Column(name, type_, nullable=False, server_default=default),
            schema="conversations",
        )
        op.alter_column("conversations", name, server_default=None, schema="conversations")
    for name, type_ in (
        ("needs_master", sa.Text()),
        ("last_message_author", sa.Text()),
        ("last_message_preview", sa.Text()),
        ("last_message_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("conversations", sa.Column(name, type_, nullable=True), schema="conversations")
    op.create_index(
        "ix_conversations_master_recent",
        "conversations",
        ["master_id", "last_message_at"],
        schema="conversations",
    )


def downgrade() -> None:
    """Удалить колонки и индексы."""
    op.drop_index("ix_conversations_master_recent", table_name="conversations", schema="conversations")
    for name in (
        "last_message_at",
        "last_message_preview",
        "last_message_author",
        "needs_master",
        *(name for name, _, _ in reversed(_SUMMARY_REQUIRED)),
    ):
        op.drop_column("conversations", name, schema="conversations")
    op.drop_index("ux_masters_owner_phone", table_name="masters", schema="tenancy")
    op.drop_column("masters", "owner_phone", schema="tenancy")
