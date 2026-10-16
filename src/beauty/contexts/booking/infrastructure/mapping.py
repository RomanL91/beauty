"""Императивный маппинг агрегата ``Appointment``."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.orm import composite

from beauty.contexts.booking.domain.appointment import Appointment
from beauty.contexts.booking.domain.value_objects import ClientSnapshot, ServiceSnapshot, TimeSlot
from beauty.contexts.booking.infrastructure.tables import appointments
from beauty.shared.infrastructure.db.metadata import mapper_registry


class BookingOrmMapper:
    """Снимки услуги и клиента, время визита — composite из нескольких колонок."""

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        columns = appointments.c
        mapper_registry.map_imperatively(
            Appointment,
            appointments,
            version_id_col=columns.version,
            properties={
                "service": composite(
                    ServiceSnapshot,
                    columns.service_id,
                    columns.service_title,
                    columns.service_duration_min,
                    columns.service_price_amount,
                ),
                "client": composite(
                    ClientSnapshot,
                    columns.client_display_name,
                    columns.client_phone_masked,
                    columns.client_visit_number,
                ),
                "slot": composite(TimeSlot, columns.start_at, columns.end_at),
            },
        )
        cls._mapped = True
