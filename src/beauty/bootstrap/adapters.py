"""Адаптеры портов между контекстами (anti-corruption layer корня композиции).

Контексты не импортируют друг друга: порт объявляет потребитель, а здесь он
реализуется запросом соседнего контекста через медиатор с переводом DTO и ошибок.
Медиатор берётся лениво — адаптеры создаются раньше, чем он собран.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import date, datetime, timedelta
from uuid import UUID

from beauty.contexts.booking.application.commands import RequestAppointment
from beauty.contexts.booking.application.errors import SlotUnavailableError
from beauty.contexts.booking.application.ports import (
    BookableSlot,
    CalendarSource,
    ClientDirectory,
    ConversationDirectory,
    SlotPolicy,
)
from beauty.contexts.booking.application.queries import ListBusyIntervals
from beauty.contexts.booking.application.schedule import CalendarDay, WorkingCalendar
from beauty.contexts.booking.domain.errors import InvalidTimeSlot
from beauty.contexts.booking.domain.value_objects import ServiceSnapshot
from beauty.contexts.conversations.application.errors import SlotNotAvailableError
from beauty.contexts.conversations.application.ports import (
    BookingDesk,
    ClientContacts,
    MasterCatalog,
    MasterInfo,
    RequestedAppointment,
    ServiceInfo,
)
from beauty.contexts.conversations.application.queries import FindConversationIds
from beauty.contexts.conversations.domain.content import OfferedSlot
from beauty.contexts.identity.application.queries import ClientNotFoundError, GetClientContact
from beauty.contexts.tenancy.application import errors as tenancy_errors
from beauty.contexts.tenancy.application.ports import BusyTimeSource
from beauty.contexts.tenancy.application.queries import (
    CheckBookableSlot,
    FindMasterByOwner,
    GetMasterPage,
    GetWorkingCalendar,
    ListFreeSlots,
)
from beauty.contexts.tenancy.domain.slots import TimeInterval
from beauty.shared.application.mediator import Mediator

type MediatorProvider = Callable[[], Mediator]


class TenancySlotPolicy(SlotPolicy):
    """Booking → Tenancy: окно проверяет тот же поиск, что показывает окна на странице."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def check(self, master_id: UUID, service_id: UUID, start: datetime) -> BookableSlot:
        """Проверенное окно или ``SlotUnavailableError``."""
        try:
            view = await self._mediator().send(CheckBookableSlot(master_id, service_id, start))
        except tenancy_errors.SlotUnavailableError as error:
            raise SlotUnavailableError(str(error)) from error
        return BookableSlot(
            service=ServiceSnapshot(
                view.service.id, view.service.title, view.service.duration_min, view.service.price_amount
            ),
            start=view.start,
            end=view.end,
            timezone=view.timezone,
            confirm_within=timedelta(hours=view.confirm_within_hours),
            change_deadline_hours=view.change_deadline_hours,
        )


class IdentityClientDirectory(ClientDirectory, ClientContacts):
    """Booking и Conversations → Identity: телефон клиента."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def phone(self, client_id: UUID) -> str:
        """Телефон в E.164."""
        return (await self._mediator().send(GetClientContact(client_id))).phone


class BookedTime(BusyTimeSource):
    """Tenancy → Booking: занятое записями время мастера."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def busy(self, master_id: UUID, start: datetime, end: datetime) -> list[TimeInterval]:
        """Интервалы заявок и записей."""
        intervals = await self._mediator().send(ListBusyIntervals(master_id, start, end))
        return [TimeInterval(i.start, i.end) for i in intervals]


class TenancyMasterCatalog(MasterCatalog):
    """Conversations → Tenancy: опубликованные мастера и их окна."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def by_slug(self, slug: str) -> MasterInfo | None:
        """Мастер по адресу."""
        return await self._page(slug)

    async def by_id(self, master_id: UUID) -> MasterInfo | None:
        """Мастер по id."""
        return await self._page(master_id)

    async def free_slots(
        self, master_id: UUID, service_id: UUID, window_from: datetime | None, limit: int
    ) -> list[OfferedSlot]:
        """Ближайшие окна."""
        slots = await self._mediator().send(
            ListFreeSlots(master_id, service_id=service_id, window_from=window_from, limit=limit)
        )
        return [OfferedSlot(slot.start, slot.end, slot.service_id) for slot in slots]

    async def _page(self, master: str | UUID) -> MasterInfo | None:
        try:
            page = await self._mediator().send(GetMasterPage(master))
        except tenancy_errors.MasterNotFoundError:
            return None
        return MasterInfo(
            id=page.id,
            slug=page.slug,
            timezone=page.timezone,
            name=page.name_nominative,
            services=tuple(ServiceInfo(s.id, s.title, s.duration_min) for s in page.services),
        )


class BookingFrontDesk(BookingDesk):
    """Conversations → Booking: заявка на запись."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def request(
        self, master_id: UUID, client_id: UUID, service_id: UUID, start: datetime
    ) -> RequestedAppointment:
        """Заявка или ``SlotNotAvailableError`` (занято, вне расписания, услуги нет)."""
        try:
            payload = await self._mediator().send(RequestAppointment(master_id, client_id, service_id, start))
        except (
            SlotUnavailableError,
            InvalidTimeSlot,
            tenancy_errors.ServiceNotFoundError,
            tenancy_errors.MasterNotFoundError,
            tenancy_errors.InvalidSlotWindowError,
        ) as error:
            raise SlotNotAvailableError(str(error)) from error
        return RequestedAppointment(UUID(payload["id"]), 1, payload)


class OwnedMasters:
    """Кабинет → Identity + Tenancy: учётная запись → телефон → страница мастера."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def __call__(self, account_id: UUID) -> UUID | None:
        """Id мастера, которым владеет учётная запись."""
        try:
            contact = await self._mediator().send(GetClientContact(account_id))
        except ClientNotFoundError:
            return None
        return await self._mediator().send(FindMasterByOwner(contact.phone))


class TenancyCalendar(CalendarSource):
    """Booking → Tenancy: рабочие часы и выходные для графика."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def calendar(self, master_id: UUID, start: date, days: int) -> WorkingCalendar:
        """Дни подряд."""
        view = await self._mediator().send(GetWorkingCalendar(master_id, start, days))
        return WorkingCalendar(
            view.timezone, tuple(CalendarDay(d.date, d.day_off, d.hours) for d in view.days)
        )


class ConversationsDirectory(ConversationDirectory):
    """Booking → Conversations: ссылка из графика в чат клиента."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def conversation_ids(self, master_id: UUID, client_ids: Collection[UUID]) -> dict[UUID, UUID]:
        """Клиент → переписка."""
        return await self._mediator().send(FindConversationIds(master_id, frozenset(client_ids)))
