"""Рабочий календарь мастера — для графика в кабинете."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from beauty.contexts.tenancy.application.dto import CalendarDayView, WorkingCalendarView
from beauty.contexts.tenancy.application.errors import InvalidSlotWindowError, MasterNotFoundError
from beauty.contexts.tenancy.application.ports import AvailabilityReader
from beauty.shared.application.cqrs import Handler, Query

MAX_DAYS = 62


@dataclass(frozen=True, slots=True)
class GetWorkingCalendar(Query[WorkingCalendarView]):
    """Рабочие часы и выходные мастера на ``days`` дней с ``start`` (черновик тоже)."""

    master_id: UUID
    start: date
    days: int = 7


class GetWorkingCalendarHandler(Handler[GetWorkingCalendar, WorkingCalendarView]):
    """Разворачивает недельное расписание и выходные даты в дни."""

    def __init__(self, reader: AvailabilityReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: GetWorkingCalendar) -> WorkingCalendarView:
        """Календарь или ``MasterNotFoundError``."""
        if not 1 <= message.days <= MAX_DAYS:
            raise InvalidSlotWindowError(f"days — от 1 до {MAX_DAYS}")
        record = await self._reader.read(message.master_id, published_only=False)
        if record is None:
            raise MasterNotFoundError()
        availability = record.availability
        days = []
        for offset in range(message.days):
            day = message.start + timedelta(days=offset)
            hours = availability.schedule.hours_on(day.weekday())
            off = day in availability.days_off or not hours
            days.append(CalendarDayView(day, off, () if off else tuple((h.start, h.end) for h in hours)))
        return WorkingCalendarView(availability.timezone.key, tuple(days))
