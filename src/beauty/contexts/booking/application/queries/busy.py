"""Занятое время мастера — для поиска окон в Tenancy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.contexts.booking.application.ports import BusyInterval, BusyTimeReader
from beauty.shared.application.cqrs import Handler, Query


@dataclass(frozen=True, slots=True)
class ListBusyIntervals(Query[list[BusyInterval]]):
    """Заявки и подтверждённые записи мастера, пересекающие ``[start, end)``."""

    master_id: UUID
    start: datetime
    end: datetime


class ListBusyIntervalsHandler(Handler[ListBusyIntervals, list[BusyInterval]]):
    """Читает занятость из read-модели."""

    def __init__(self, reader: BusyTimeReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: ListBusyIntervals) -> list[BusyInterval]:
        """Вернуть интервалы."""
        return await self._reader.read(message.master_id, message.start, message.end)
