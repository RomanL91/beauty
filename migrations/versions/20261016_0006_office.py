"""Кабинет ИИ-администратора: профиль кабинета, тикеты без клиента, лента поручений,
отмена записи мастером.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS = "'client_cancelled', 'declined', 'expired', 'rescheduled'"


def upgrade() -> None:
    """Профиль кабинета, лента поручений, причина отмены ``master_cancelled``."""
    op.add_column(
        "profiles",
        sa.Column("office_profile_name", sa.Text(), comment="профиль кабинета (поручения мастера)"),
        schema="agent",
    )
    op.add_column("profiles", sa.Column("office_runs_api_key", sa.Text()), schema="agent")
    op.add_column(
        "profiles",
        sa.Column("office_mcp_token", sa.Text(), comment="SHA-256 MCP-токена кабинета"),
        schema="agent",
    )
    op.create_unique_constraint(
        op.f("uq_profiles_office_profile_name"), "profiles", ["office_profile_name"], schema="agent"
    )
    op.create_unique_constraint(
        op.f("uq_profiles_office_mcp_token"), "profiles", ["office_mcp_token"], schema="agent"
    )

    op.alter_column(
        "tickets", "conversation_id", nullable=True, comment="ресепшн: переписка хода", schema="agent"
    )
    op.alter_column("tickets", "client_id", nullable=True, comment="ресепшн: клиент хода", schema="agent")
    op.add_column(
        "tickets",
        sa.Column("asked_master", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema="agent",
    )

    op.create_table(
        "office_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("client_message_id", sa.UUID(), nullable=True),
        sa.Column("ai_generated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_office_messages")),
        schema="agent",
        comment="Лента поручений мастера его ИИ-администратору",
    )
    op.create_index("ix_office_messages_master", "office_messages", ["master_id", "id"], schema="agent")
    op.create_index(
        "ux_office_messages_client_message_id",
        "office_messages",
        ["master_id", "client_message_id"],
        unique=True,
        schema="agent",
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )

    op.drop_constraint(op.f("ck_appointments_cancel_reason"), "appointments", schema="booking")
    op.create_check_constraint(
        op.f("ck_appointments_cancel_reason"),
        "appointments",
        f"cancel_reason IN ({_REASONS}, 'master_cancelled')",
        schema="booking",
    )


def downgrade() -> None:
    """Вернуть схему итерации 4 (ленту поручений и отмены мастером — удалить)."""
    op.execute("DELETE FROM booking.appointments WHERE cancel_reason = 'master_cancelled'")
    op.drop_constraint(op.f("ck_appointments_cancel_reason"), "appointments", schema="booking")
    op.create_check_constraint(
        op.f("ck_appointments_cancel_reason"), "appointments", f"cancel_reason IN ({_REASONS})", schema="booking"
    )
    op.drop_index("ux_office_messages_client_message_id", table_name="office_messages", schema="agent")
    op.drop_index("ix_office_messages_master", table_name="office_messages", schema="agent")
    op.drop_table("office_messages", schema="agent")
    op.execute("DELETE FROM agent.tickets WHERE conversation_id IS NULL OR client_id IS NULL")
    op.drop_column("tickets", "asked_master", schema="agent")
    op.alter_column("tickets", "client_id", nullable=False, comment=None, schema="agent")
    op.alter_column("tickets", "conversation_id", nullable=False, comment=None, schema="agent")
    op.drop_constraint(op.f("uq_profiles_office_mcp_token"), "profiles", schema="agent")
    op.drop_constraint(op.f("uq_profiles_office_profile_name"), "profiles", schema="agent")
    op.drop_column("profiles", "office_mcp_token", schema="agent")
    op.drop_column("profiles", "office_runs_api_key", schema="agent")
    op.drop_column("profiles", "office_profile_name", schema="agent")
