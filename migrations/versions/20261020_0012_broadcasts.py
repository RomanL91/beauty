"""Рассылки объявлений мастеров: рассылки и запрет рассылок администрацией.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицы рассылок."""
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("photo_key", sa.Text(), comment="фото в хранилище файлов (подписанные ссылки)"),
        sa.Column("status", sa.Text(), nullable=False, comment="draft | sending | sent"),
        sa.Column("origin", sa.Text(), nullable=False, comment="master | agent"),
        sa.Column("recipients", sa.Integer(), nullable=False),
        sa.Column("delivered", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.UUID(), comment="последняя переписка, получившая объявление"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broadcasts")),
        schema="conversations",
        comment="Рассылки объявлений мастеров всем их клиентам",
    )
    op.create_index(
        "ix_broadcasts_master_created", "broadcasts", ["master_id", "created_at"], schema="conversations"
    )
    op.create_table(
        "broadcast_blocks",
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("master_id", name=op.f("pk_broadcast_blocks")),
        schema="conversations",
        comment="Мастера, которым администрация запретила рассылки",
    )


def downgrade() -> None:
    """Удалить таблицы рассылок."""
    op.drop_table("broadcast_blocks", schema="conversations")
    op.drop_index("ix_broadcasts_master_created", table_name="broadcasts", schema="conversations")
    op.drop_table("broadcasts", schema="conversations")
