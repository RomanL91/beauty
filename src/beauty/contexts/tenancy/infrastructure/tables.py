"""Таблицы схемы ``tenancy``.

* ``masters`` — агрегат целиком, кроме услуг: профиль, правила записи (колонки —
  их читают запросы окон), недельное расписание, выходные и фото — ``jsonb``
  (value objects читаются и пишутся целиком, отдельные таблицы не нужны);
* ``master_services`` — услуги (сущности агрегата). На услугу будут ссылаться
  записи, поэтому её не удаляют, а архивируют; частичный индекс по активным
  услугам в порядке показа обслуживает и страницу, и поиск окон.

Внешний ключ услуги на мастера — внутри одного агрегата, поэтому обычный, а
не отложенный: SQLAlchemy вставляет мастера раньше его услуг (relationship).
"""

from __future__ import annotations

from operator import attrgetter

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import UUID

from beauty.contexts.tenancy.domain.value_objects import (
    MasterSlug,
    MasterStatus,
    Money,
    ServiceDuration,
    TimeZoneName,
)
from beauty.contexts.tenancy.infrastructure.serialization import (
    dump_days,
    dump_photos,
    dump_schedule,
    load_days,
    load_photos,
    load_schedule,
)
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import (
    BigIntegerValueObjectType,
    IntegerValueObjectType,
    JsonValueObjectType,
    StringValueObjectType,
)

SCHEMA = "tenancy"

_value = attrgetter("value")
MasterSlugType = StringValueObjectType(MasterSlug, _value)
TimeZoneType = StringValueObjectType(TimeZoneName, _value)
ServiceDurationType = IntegerValueObjectType(ServiceDuration, attrgetter("minutes"))
PriceType = BigIntegerValueObjectType(Money, attrgetter("amount"))
ScheduleType = JsonValueObjectType(dump_schedule, load_schedule)
DaysOffType = JsonValueObjectType(dump_days, load_days)
PhotosType = JsonValueObjectType(dump_photos, load_photos)

MasterStatusType = Enum(
    MasterStatus,
    name="master_status",
    native_enum=False,
    create_constraint=True,
    length=16,
    values_callable=lambda members: [member.value for member in members],
    validate_strings=True,
)

masters = Table(
    "masters",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("slug", MasterSlugType, nullable=False, unique=True),
    Column("status", MasterStatusType, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("name_nominative", Text, nullable=False),
    Column("name_genitive", Text, nullable=False),
    Column("name_dative", Text, nullable=False),
    Column("specialty", Text, nullable=False),
    Column("address", Text, nullable=False),
    Column("about", Text, nullable=False),
    Column("avatar_url", Text),
    Column("timezone", TimeZoneType, nullable=False),
    Column("confirm_within_hours", Integer, nullable=False),
    Column("change_deadline_hours", Integer, nullable=False),
    Column("min_notice_minutes", Integer, nullable=False),
    Column("horizon_days", Integer, nullable=False),
    Column("slot_step_minutes", Integer, nullable=False),
    Column("schedule", ScheduleType, nullable=False),
    Column("days_off", DaysOffType, nullable=False),
    Column("photos", PhotosType, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    schema=SCHEMA,
    comment="Мастера-арендаторы и их публичные страницы",
)

master_services = Table(
    "master_services",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("master_id", UUID(as_uuid=True), ForeignKey(masters.c.id, ondelete="CASCADE"), nullable=False),
    Column("title", Text, nullable=False),
    Column("duration_min", ServiceDurationType, nullable=False),
    Column("price_amount", PriceType, comment="тиыны; NULL — цена по запросу"),
    Column("position", Integer, nullable=False),
    Column("archived_at", DateTime(timezone=True)),
    schema=SCHEMA,
    comment="Услуги мастеров (архивируются, не удаляются)",
)

Index(
    "ix_master_services_active",
    master_services.c.master_id,
    master_services.c.position,
    postgresql_where=text("archived_at IS NULL"),
)
Index("ix_master_services_master_id", master_services.c.master_id)
