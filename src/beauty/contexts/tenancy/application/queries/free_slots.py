"""Свободные окна мастера."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from beauty.contexts.tenancy.application.dto import BookableSlotView, SlotView
from beauty.contexts.tenancy.application.errors import (
    InvalidSlotWindowError,
    MasterNotFoundError,
    ServiceNotFoundError,
    SlotUnavailableError,
)
from beauty.contexts.tenancy.application.ports import (
    AvailabilityReader,
    BookableService,
    BusyTimeSource,
    MasterPageReader,
    MasterRef,
)
from beauty.contexts.tenancy.domain.slots import SlotFinder, SlotSearch
from beauty.shared.application.cqrs import Handler, Query
from beauty.shared.domain.clock import Clock

MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class ListFreeSlots(Query[list[SlotView]]):
    """Свободные окна; без услуги — по самой короткой."""

    master: MasterRef
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
        record = await self._reader.read(message.master)
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


@dataclass(frozen=True, slots=True)
class CheckBookableSlot(Query[BookableSlotView]):
    """Можно ли записаться на услугу к ``start`` (для контекста записи).

    Окно должно быть ровно таким, какое показал бы поиск: в рабочих часах, по сетке,
    не раньше min notice, в пределах горизонта и не занято.
    """

    master_id: UUID
    service_id: UUID
    start: datetime


class CheckBookableSlotHandler(Handler[CheckBookableSlot, BookableSlotView]):
    """Проверяет окно тем же доменным сервисом, что и поиск."""

    def __init__(
        self,
        pages: MasterPageReader,
        reader: AvailabilityReader,
        busy: BusyTimeSource,
        finder: SlotFinder,
        clock: Clock,
    ) -> None:
        """Получить зависимости."""
        self._pages = pages
        self._reader = reader
        self._busy = busy
        self._finder = finder
        self._clock = clock

    async def handle(self, message: CheckBookableSlot) -> BookableSlotView:
        """Снимок услуги и правил или ``SlotUnavailableError``."""
        if message.start.tzinfo is None:
            raise InvalidSlotWindowError("Время — с часовым поясом (RFC 3339)")
        page = await self._pages.read(message.master_id)
        record = await self._reader.read(message.master_id)
        if page is None or record is None:
            raise MasterNotFoundError()
        service = next((s for s in page.services if s.id == message.service_id), None)
        if service is None:
            raise ServiceNotFoundError()
        start = message.start.astimezone(UTC)
        search = SlotSearch(
            duration=timedelta(minutes=service.duration_min),
            now=self._clock.now(),
            window_from=start,
            window_to=start + timedelta(minutes=1),
            limit=1,
        )
        earliest, latest = self._finder.bounds(record.availability, search)
        if earliest >= latest:
            raise SlotUnavailableError()
        busy = await self._busy.busy(record.master_id, earliest, latest)
        found = self._finder.find(record.availability, search, busy)
        if not found or found[0].start.astimezone(UTC) != start:
            raise SlotUnavailableError()
        return BookableSlotView(
            master_id=record.master_id,
            service=service,
            start=found[0].start,
            end=found[0].end,
            timezone=page.timezone,
            confirm_within_hours=page.confirm_within_hours,
            change_deadline_hours=page.change_deadline_hours,
        )
