"""Таблицы схемы ``booking``.

Главное ограничение — исключающее: у мастера не может быть двух открытых
(заявка или подтверждена) записей, пересекающихся по времени. Это и есть защита от
двойной записи под конкурентной нагрузкой: две транзакции, вставляющие
пересекающиеся записи, не пройдут обе — вторая получит ``exclusion_violation``.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Enum, Index, Integer, Table, Text, func, text
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint

from beauty.contexts.booking.domain.value_objects import AppointmentStatus, CancelledBy, CancelReason
from beauty.shared.infrastructure.db.metadata import metadata

NO_OVERLAP_CONSTRAINT = "ex_appointments_no_overlap"


def _enum(enum: type[AppointmentStatus | CancelledBy | CancelReason], name: str) -> Enum:
    """Строковое перечисление с CHECK (без нативного типа PostgreSQL)."""
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=24,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


appointments = Table(
    "appointments",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("master_id", UUID(as_uuid=True), nullable=False),
    Column("client_id", UUID(as_uuid=True), nullable=False),
    Column("status", _enum(AppointmentStatus, "appointment_status"), nullable=False),
    Column("service_id", UUID(as_uuid=True), nullable=False),
    Column("service_title", Text, nullable=False),
    Column("service_duration_min", Integer, nullable=False),
    Column("service_price_amount", BigInteger),
    Column("client_display_name", Text, nullable=False),
    Column("client_phone_masked", Text, nullable=False),
    Column("client_visit_number", Integer, nullable=False),
    Column("start_at", DateTime(timezone=True), nullable=False),
    Column("end_at", DateTime(timezone=True), nullable=False),
    Column("timezone", Text, nullable=False),
    Column("hold_until", DateTime(timezone=True), nullable=False),
    Column("change_deadline_hours", Integer, nullable=False),
    Column("reschedule_of", UUID(as_uuid=True)),
    Column("confirmed_at", DateTime(timezone=True)),
    Column("cancelled_at", DateTime(timezone=True)),
    Column("cancelled_by", _enum(CancelledBy, "cancelled_by")),
    Column("cancel_reason", _enum(CancelReason, "cancel_reason")),
    Column("completed_at", DateTime(timezone=True)),
    Column("revision", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    Index("ix_appointments_master_start", "master_id", "start_at"),
    Index("ix_appointments_client_master", "client_id", "master_id", "start_at"),
    Index(
        "ix_appointments_reschedule_of",
        "reschedule_of",
        postgresql_where=text("reschedule_of IS NOT NULL AND status = 'requested'"),
    ),
    schema="booking",
    comment="Заявки и записи клиентов к мастерам",
)

appointments.append_constraint(
    ExcludeConstraint(
        (appointments.c.master_id, "="),
        (func.tstzrange(appointments.c.start_at, appointments.c.end_at), "&&"),
        name=NO_OVERLAP_CONSTRAINT,
        using="gist",
        where=text("status IN ('requested', 'confirmed')"),
    )
)
