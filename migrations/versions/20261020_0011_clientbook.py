"""Картотека клиентов мастера: схема clientbook (имя клиента у мастера, заметки).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать схему clientbook."""
    op.execute("CREATE SCHEMA IF NOT EXISTS clientbook")
    op.create_table(
        "files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), comment="имя клиента у мастера; NULL — подпись по телефону"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
        sa.UniqueConstraint("master_id", "client_id", name="uq_files_master_client"),
        schema="clientbook",
        comment="Карточки клиентов у мастеров (заводятся при первом имени или заметке)",
    )
    op.create_table(
        "notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False, comment="master | agent"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id"], ["clientbook.files.id"], name=op.f("fk_notes_file_id_files"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
        schema="clientbook",
        comment="Заметки о клиентах: мастера и ИИ-администратора",
    )
    op.create_index("ix_notes_file_created", "notes", ["file_id", "created_at"], schema="clientbook")


def downgrade() -> None:
    """Удалить схему clientbook."""
    op.drop_index("ix_notes_file_created", table_name="notes", schema="clientbook")
    op.drop_table("notes", schema="clientbook")
    op.drop_table("files", schema="clientbook")
    op.execute("DROP SCHEMA IF EXISTS clientbook")
