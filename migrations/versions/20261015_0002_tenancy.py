"""Схема tenancy: мастера и их услуги.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать схему, таблицы мастеров и услуг, индексы."""
    op.execute("CREATE SCHEMA IF NOT EXISTS tenancy")
    op.create_table(
        "masters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("name_nominative", sa.Text(), nullable=False),
        sa.Column("name_genitive", sa.Text(), nullable=False),
        sa.Column("name_dative", sa.Text(), nullable=False),
        sa.Column("specialty", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("about", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("confirm_within_hours", sa.Integer(), nullable=False),
        sa.Column("change_deadline_hours", sa.Integer(), nullable=False),
        sa.Column("min_notice_minutes", sa.Integer(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("slot_step_minutes", sa.Integer(), nullable=False),
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("days_off", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("photos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'published')", name=op.f("ck_masters_master_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_masters")),
        sa.UniqueConstraint("slug", name=op.f("uq_masters_slug")),
        schema="tenancy",
        comment="Мастера-арендаторы и их публичные страницы",
    )
    op.create_table(
        "master_services",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("master_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("price_amount", sa.BigInteger(), nullable=True, comment="тиыны; NULL — цена по запросу"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["master_id"],
            ["tenancy.masters.id"],
            name=op.f("fk_master_services_master_id_masters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_master_services")),
        schema="tenancy",
        comment="Услуги мастеров (архивируются, не удаляются)",
    )
    op.create_index(
        "ix_master_services_active",
        "master_services",
        ["master_id", "position"],
        schema="tenancy",
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index("ix_master_services_master_id", "master_services", ["master_id"], schema="tenancy")


def downgrade() -> None:
    """Удалить схему tenancy."""
    op.drop_table("master_services", schema="tenancy")
    op.drop_table("masters", schema="tenancy")
    op.execute("DROP SCHEMA IF EXISTS tenancy")
