"""Репозиторий записей на SQLAlchemy."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from beauty.contexts.booking.domain.appointment import Appointment
from beauty.contexts.booking.domain.repositories import AppointmentRepository
from beauty.contexts.booking.domain.value_objects import AppointmentStatus
from beauty.contexts.booking.infrastructure.tables import appointments
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyAppointmentRepository(SqlAlchemyRepository[Appointment], AppointmentRepository):
    """Записи."""

    async def get(self, appointment_id: UUID) -> Appointment | None:
        """По первичному ключу."""
        return self._seen(await self._session.get(Appointment, appointment_id))

    async def pending_reschedules(self, appointment_id: UUID) -> list[Appointment]:
        """Неподтверждённые переносы (частичный индекс ``ix_appointments_reschedule_of``)."""
        statement = select(Appointment).where(
            appointments.c.reschedule_of == appointment_id,
            appointments.c.status == AppointmentStatus.REQUESTED,
        )
        found = (await self._session.execute(statement)).scalars().all()
        return [self._tracker.track(appointment) for appointment in found]

    async def visits_before(self, master_id: UUID, client_id: UUID, moment: datetime) -> int:
        """Подтверждённые и состоявшиеся визиты клиента к мастеру до ``moment``."""
        statement = select(func.count()).where(
            appointments.c.client_id == client_id,
            appointments.c.master_id == master_id,
            appointments.c.start_at < moment,
            appointments.c.status.in_((AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED)),
        )
        return int((await self._session.execute(statement)).scalar_one())
