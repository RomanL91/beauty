"""Схема agent: профили Hermes мастеров и тикеты ходов.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать схему и таблицы."""
    op.execute("CREATE SCHEMA IF NOT EXISTS agent")
    op.create_table(
        "profiles",
        sa.Column("id", sa.UUID(), nullable=False, comment="id мастера"),
        sa.Column("profile_name", sa.Text(), nullable=False),
        sa.Column("runs_api_key", sa.Text(), nullable=False, comment="ключ Runs API профиля Hermes"),
        sa.Column("mcp_token", sa.Text(), nullable=False, comment="SHA-256 MCP-токена профиля"),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profiles")),
        sa.UniqueConstraint("profile_name", name=op.f("uq_profiles_profile_name")),
        sa.UniqueConstraint("mcp_token", name=op.f("uq_profiles_mcp_token")),
        schema="agent",
        comment="ИИ-администраторы мастеров (профили Hermes)",
    )
    op.create_table(
        "tickets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("face", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handed_off", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        schema="agent",
        comment="Тикеты ходов агента (права одного хода)",
    )


def downgrade() -> None:
    """Удалить схему agent."""
    op.execute("DROP SCHEMA IF EXISTS agent CASCADE")
