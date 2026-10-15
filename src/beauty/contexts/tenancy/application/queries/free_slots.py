"""Свободные окна мастера."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from beauty.contexts.tenancy.application.dto import SlotView
from beauty.contexts.tenancy.application.errors import (
    InvalidSlotWindowError,
    MasterNotFoundError,
    ServiceNotFoundError,
)
from beauty.contexts.tenancy.application.ports import AvailabilityReader, BookableService, BusyTimeSource
from beauty.contexts.tenancy.domain.slots import SlotFinder, SlotSearch
from beauty.shared.application.cqrs import Handler, Query
from beauty.shared.domain.clock import Clock

MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class ListFreeSlots(Query[list[SlotView]]):
    """Свободные окна; без услуги — по самой короткой."""

    slug: str
    service_id: UUID | None = None
    window_from: datetime | None = None
    window_to: datetime | None = None
    limit: int = 20


class ListFreeSlotsHandler(Handler[ListFreeSlots, list[SlotView]]):
    """Собирает снимок доступности и занятое время, окна считает доменный сервис."""

    def __init__(
        self, reader: AvailabilityReader, busy: BusyTimeSource, finder: SlotFinder, clock: Clock
    ) -> None:
        """Получить зависимости."""
        self._reader = reader
        self._busy = busy
        self._finder = finder
        self._clock = clock

    async def handle(self, message: ListFreeSlots) -> list[SlotView]:
        """Найти окна."""
        self._validate(message)
        record = await self._reader.read(message.slug)
        if record is None:
            raise MasterNotFoundError()
        service = self._service(record.services, message.service_id)
        search = SlotSearch(
            duration=timedelta(minutes=service.duration_min),
            now=self._clock.now(),
            window_from=message.window_from,
            window_to=message.window_to,
            limit=message.limit,
        )
        earliest, latest = self._finder.bounds(record.availability, search)
        if earliest >= latest:
            return []
        busy = await self._busy.busy(record.master_id, earliest, latest)
        slots = self._finder.find(record.availability, search, busy)
        return [SlotView(start=s.start, end=s.end, service_id=service.id) for s in slots]

    @staticmethod
    def _validate(message: ListFreeSlots) -> None:
        if not 1 <= message.limit <= MAX_LIMIT:
            raise InvalidSlotWindowError(f"limit — от 1 до {MAX_LIMIT}")
        for moment in (message.window_from, message.window_to):
            if moment is not None and moment.tzinfo is None:
                raise InvalidSlotWindowError("Время — с часовым поясом (RFC 3339)")
        if message.window_from and message.window_to and message.window_from >= message.window_to:
            raise InvalidSlotWindowError("from должен быть раньше to")

    @staticmethod
    def _service(services: tuple[BookableService, ...], service_id: UUID | None) -> BookableService:
        if service_id is not None:
            for service in services:
                if service.id == service_id:
                    return service
            raise ServiceNotFoundError()
        if not services:
            raise ServiceNotFoundError("У мастера нет активных услуг")
        return min(services, key=lambda s: s.duration_min)
