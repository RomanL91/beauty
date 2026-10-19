"""Админ-панель: схема admin (администраторы, сессии, журнал), блокировка клиентов,
журнал ходов агента.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать схему admin, таблицу agent.runs, колонки блокировки клиента."""
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")
    op.create_table(
        "administrators",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("login", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False, comment="scrypt$n$r$p$соль$ключ"),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_administrators")),
        sa.UniqueConstraint("login", name=op.f("uq_administrators_login")),
        schema="admin",
        comment="Администраторы панели хозяина сервиса",
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("admin_id", sa.UUID(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False, comment="SHA-256 секрета из cookie"),
        sa.Column("csrf_token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admin.administrators.id"], name=op.f("fk_sessions_admin_id_administrators")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        schema="admin",
        comment="Сессии администраторов (cookie bk_admin)",
    )
    op.create_index("ix_admin_sessions_admin", "sessions", ["admin_id"], schema="admin")
    op.create_table(
        "audit",
        sa.Column("id", sa.UUID(), nullable=False, comment="UUIDv7: порядок — по времени"),
        sa.Column("admin_id", sa.UUID(), nullable=False),
        sa.Column("admin_login", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target", sa.Text()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit")),
        schema="admin",
        comment="Журнал действий администраторов",
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Text(), nullable=False, comment="id тикета хода"),
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("face", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.UUID()),
        sa.Column("status", sa.Text(), nullable=False, comment="completed или статус сбоя"),
        sa.Column("seconds", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        schema="agent",
        comment="Журнал ходов агента (итог и длительность)",
    )
    op.create_index("ix_runs_created_at", "runs", ["created_at"], schema="agent")
    op.add_column(
        "client_accounts",
        sa.Column("blocked_at", sa.DateTime(timezone=True), comment="заблокирован хозяином сервиса"),
        schema="identity",
    )
    op.add_column("client_accounts", sa.Column("blocked_reason", sa.Text()), schema="identity")


def downgrade() -> None:
    """Убрать."""
    op.drop_column("client_accounts", "blocked_reason", schema="identity")
    op.drop_column("client_accounts", "blocked_at", schema="identity")
    op.drop_index("ix_runs_created_at", table_name="runs", schema="agent")
    op.drop_table("runs", schema="agent")
    op.drop_table("audit", schema="admin")
    op.drop_index("ix_admin_sessions_admin", table_name="sessions", schema="admin")
    op.drop_table("sessions", schema="admin")
    op.drop_table("administrators", schema="admin")
    op.execute("DROP SCHEMA IF EXISTS admin")
