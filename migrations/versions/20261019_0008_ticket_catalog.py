"""Отпечаток страницы мастера у тикета хода: следующий ход узнаёт, что страница изменилась.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить ``catalog``."""
    op.add_column(
        "tickets",
        sa.Column("catalog", sa.Text(), comment="отпечаток страницы мастера в инструкциях хода"),
        schema="agent",
    )


def downgrade() -> None:
    """Убрать ``catalog``."""
    op.drop_column("tickets", "catalog", schema="agent")
