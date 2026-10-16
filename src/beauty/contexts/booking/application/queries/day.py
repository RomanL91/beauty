"""График дня мастера (``DaySchedule`` контракта)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.booking.application.ports import CalendarSource, ConversationDirectory, MasterDayReader
from beauty.contexts.booking.application.schedule import build_day
from beauty.shared.application.cqrs import Handler, Query


@dataclass(frozen=True, slots=True)
class GetDaySchedule(Query[dict[str, Any]]):
    """День ``day`` (локальная дата мастера) и его неделя."""

    master_id: UUID
    day: date


class GetDayScheduleHandler(Handler[GetDaySchedule, dict[str, Any]]):
    """Собирает день из календаря, записей и переписок."""

    def __init__(
        self, calendar: CalendarSource, reader: MasterDayReader, conversations: ConversationDirectory
    ) -> None:
        """Получить зависимости."""
        self._calendar = calendar
        self._reader = reader
        self._conversations = conversations

    async def handle(self, message: GetDaySchedule) -> dict[str, Any]:
        """День в форме контракта."""
        monday = message.day - timedelta(days=message.day.weekday())
        calendar = await self._calendar.calendar(message.master_id, monday, 7)
        zone = ZoneInfo(calendar.timezone)
        today = next(d for d in calendar.days if d.date == message.day)
        start = datetime.combine(message.day, time(), tzinfo=zone)
        end = datetime.combine(message.day + timedelta(days=1), time(), tzinfo=zone)
        appointments = await self._reader.appointments(message.master_id, start, end)
        links = await self._conversations.conversation_ids(
            message.master_id, {a.client_id for a in appointments}
        )
        items, summary = build_day(today, zone, appointments, links)
        return {
            "date": message.day.isoformat(),
            "week": [{"date": d.date.isoformat(), "day_off": d.day_off} for d in calendar.days],
            "day_off": today.day_off,
            "items": items,
            "summary": summary,
        }
