"""Описание услуги: мастер пишет для клиентов и ИИ-администратора.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить ``description``."""
    op.add_column(
        "master_services",
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="для кого, как проходит, противопоказания; пусто — нет описания",
        ),
        schema="tenancy",
    )


def downgrade() -> None:
    """Убрать ``description``."""
    op.drop_column("master_services", "description", schema="tenancy")
