"""Read-модели Booking."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.booking.application.ports import BusyInterval, BusyTimeReader, MasterDayReader
from beauty.contexts.booking.application.schedule import DayAppointment
from beauty.contexts.booking.domain.appointment import Appointment
from beauty.contexts.booking.domain.value_objects import AppointmentStatus
from beauty.contexts.booking.infrastructure.tables import appointments


class SqlBusyTimeReader(BusyTimeReader):
    """Открытые записи мастера в окне — по индексу ``(master_id, start_at)``.

    Неподтверждённые заявки занимают окно так же, как записи: это то же условие, что
    в исключающем ограничении, поэтому поиск не покажет окно, которое БД не даст занять.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Получить фабрику сессий."""
        self._session_factory = session_factory

    async def read(self, master_id: UUID, start: datetime, end: datetime) -> list[BusyInterval]:
        """Интервалы, пересекающие ``[start, end)``."""
        columns = appointments.c
        statement = (
            select(columns.start_at, columns.end_at)
            .where(
                columns.master_id == master_id,
                columns.status.in_((AppointmentStatus.REQUESTED, AppointmentStatus.CONFIRMED)),
                columns.start_at < end,
                columns.end_at > start,
            )
            .order_by(columns.start_at)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [BusyInterval(row.start_at, row.end_at) for row in rows]


class SqlMasterDayReader(MasterDayReader):
    """Записи мастера за период — агрегаты без трекинга (снимок строит сам агрегат)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Получить фабрику сессий."""
        self._session_factory = session_factory

    async def appointments(self, master_id: UUID, start: datetime, end: datetime) -> list[DayAppointment]:
        """Заявки, подтверждённые и состоявшиеся записи по индексу ``(master_id, start_at)``."""
        columns = appointments.c
        statement = (
            select(Appointment)
            .where(
                columns.master_id == master_id,
                columns.start_at >= start,
                columns.start_at < end,
                columns.status != AppointmentStatus.CANCELLED,
            )
            .order_by(columns.start_at)
        )
        async with self._session_factory() as session:
            found = (await session.execute(statement)).scalars().all()
            return [DayAppointment(a.snapshot(), a.client_id, a.slot.start, a.slot.end) for a in found]
