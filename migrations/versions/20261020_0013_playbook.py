"""Опыт мастера для его ИИ-администратора: записи словами мастера и самостоятельность записи.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Таблицы agent.playbooks и agent.practices."""
    op.create_table(
        "playbooks",
        sa.Column("id", sa.UUID(), nullable=False, comment="id мастера"),
        sa.Column(
            "auto_confirm", sa.Boolean(), nullable=False, comment="агент сам подтверждает записи клиентов"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playbooks")),
        schema="agent",
        comment="Опыт мастера для его ИИ-администратора",
    )
    op.create_table(
        "practices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("playbook_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), comment="услуга мастера; NULL — общая запись"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False, comment="master | agent"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["playbook_id"],
            ["agent.playbooks.id"],
            name=op.f("fk_practices_playbook_id_playbooks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_practices")),
        schema="agent",
        comment="Записи опыта мастера: общие и к услугам",
    )
    op.create_index(
        "ix_practices_playbook_created", "practices", ["playbook_id", "created_at"], schema="agent"
    )


def downgrade() -> None:
    """Удалить опыт мастера."""
    op.drop_index("ix_practices_playbook_created", table_name="practices", schema="agent")
    op.drop_table("practices", schema="agent")
    op.drop_table("playbooks", schema="agent")
