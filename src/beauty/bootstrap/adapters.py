"""Адаптеры портов между контекстами (anti-corruption layer корня композиции).

Контексты не импортируют друг друга: порт объявляет потребитель, а здесь он
реализуется запросом соседнего контекста через медиатор с переводом DTO и ошибок.
Медиатор берётся лениво — адаптеры создаются раньше, чем он собран.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.admin.application import ports as admin_ports
from beauty.contexts.agent.application import ports as agent_ports
from beauty.contexts.agent.application.commands import SetAgentEnabled
from beauty.contexts.booking.application.commands import (
    CancelAppointment,
    CancelAppointmentByMaster,
    ConfirmAppointment,
    DeclineAppointment,
    RequestAppointment,
)
from beauty.contexts.booking.application.errors import AppointmentNotFoundError, SlotUnavailableError
from beauty.contexts.booking.application.ports import (
    BookableSlot,
    CalendarSource,
    ClientDirectory,
    ConversationDirectory,
    SlotPolicy,
)
from beauty.contexts.booking.application.queries import (
    GetDaySchedule,
    ListBusyIntervals,
    ListClientAppointments,
)
from beauty.contexts.booking.application.schedule import CalendarDay, WorkingCalendar
from beauty.contexts.booking.domain.errors import (
    AppointmentClosed,
    AppointmentNotPending,
    ChangeDeadlinePassed,
    InvalidTimeSlot,
    RequestExpired,
)
from beauty.contexts.booking.domain.value_objects import ServiceSnapshot
from beauty.contexts.clientbook.application import errors as clientbook_errors
from beauty.contexts.clientbook.application.commands import AddClientNote, RenameClient
from beauty.contexts.clientbook.application.ports import Roster
from beauty.contexts.clientbook.application.queries import GetClientCard, GetClientName, ListClientNotes
from beauty.contexts.clientbook.domain import errors as clientbook_domain
from beauty.contexts.conversations.application.commands import (
    DraftBroadcast,
    HandOffToMaster,
    PostAgentReply,
    PostOnMasterBehalf,
    SetBroadcastsAllowed,
)
from beauty.contexts.conversations.application.errors import ConversationNotFoundError, SlotNotAvailableError
from beauty.contexts.conversations.application.ports import (
    BookingDesk,
    ClientContacts,
    MasterCatalog,
    MasterInfo,
    RequestedAppointment,
    ServiceInfo,
)
from beauty.contexts.conversations.application.queries import (
    FindConversationIds,
    GetBroadcast,
    GetConversationState,
    GetConversationSummary,
    ListInbox,
    RecentAnnouncements,
)
from beauty.contexts.conversations.domain.content import OfferedSlot
from beauty.contexts.conversations.domain.errors import InvalidBroadcast
from beauty.contexts.identity.application.commands import SetAccountBlocked
from beauty.contexts.identity.application.queries import ClientNotFoundError, GetClientContact
from beauty.contexts.notifications.application import ports as notification_ports
from beauty.contexts.tenancy.application import errors as tenancy_errors
from beauty.contexts.tenancy.application.commands import (
    AssignOwner,
    ChangeDayOff,
    PublishMaster,
    RegisterMaster,
    UnpublishMaster,
    UpdateMasterProfile,
)
from beauty.contexts.tenancy.application.ports import BusyTimeSource
from beauty.contexts.tenancy.application.queries import (
    CheckBookableSlot,
    FindMasterByOwner,
    FindMasterId,
    GetMasterPage,
    GetMasterSettings,
    GetWorkingCalendar,
    ListFreeSlots,
)
from beauty.contexts.tenancy.domain.slots import TimeInterval
from beauty.contexts.tenancy.presentation.api.schemas import MasterSettingsResponse
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
    """Booking и Conversations → Identity: телефон клиента; Booking → Clientbook: имя у мастера."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def phone(self, client_id: UUID) -> str:
        """Телефон в E.164."""
        return (await self._mediator().send(GetClientContact(client_id))).phone

    async def name(self, master_id: UUID, client_id: UUID) -> str | None:
        """Имя из картотеки мастера."""
        return await self._mediator().send(GetClientName(master_id, client_id))


class ConversationsRoster(Roster):
    """Clientbook → Conversations: клиент мастера — тот, у кого с ним есть переписка."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def has_client(self, master_id: UUID, client_id: UUID) -> bool:
        """Есть ли переписка."""
        found = await self._mediator().send(FindConversationIds(master_id, frozenset({client_id})))
        return client_id in found


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


class AgentMasters(agent_ports.MasterBriefs):
    """Agent → Tenancy: мастер для инструкций хода."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def brief(self, master_id: UUID) -> agent_ports.MasterBrief | None:
        """Страница мастера (и черновик)."""
        try:
            page = await self._mediator().send(GetMasterPage(master_id, published_only=False))
        except tenancy_errors.MasterNotFoundError:
            return None
        return agent_ports.MasterBrief(
            id=page.id,
            name=page.name_nominative,
            specialty=page.specialty,
            address=page.address,
            timezone=page.timezone,
            services=tuple(
                agent_ports.ServiceBrief(s.id, s.title, s.duration_min, s.price_amount, s.description)
                for s in page.services
            ),
            confirm_within_hours=page.confirm_within_hours,
            change_deadline_hours=page.change_deadline_hours,
            about=page.about,
            announcements=tuple(
                f"{item.started_at.astimezone(ZoneInfo(page.timezone)):%d.%m}: {item.text}"
                + (" (с фото)" if item.has_photo else "")
                for item in await self._mediator().send(RecentAnnouncements(master_id))
            ),
        )


class AgentConversations(agent_ports.Conversations):
    """Agent → Conversations: состояние переписки, ответ, передача мастеру."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def state(self, conversation_id: UUID) -> agent_ports.ConversationInfo:
        """Чья переписка и кто ведёт."""
        state = await self._mediator().send(GetConversationState(conversation_id))
        return agent_ports.ConversationInfo(
            state.master_id, state.client_id, state.client_name, state.handler
        )

    async def reply(self, conversation_id: UUID, text: str, *, resolve_question: bool) -> bool:
        """Ответ агента."""
        return await self._mediator().send(
            PostAgentReply(conversation_id, text, resolve_question=resolve_question)
        )

    async def hand_off(self, conversation_id: UUID, note: str) -> None:
        """Передача мастеру."""
        await self._mediator().send(HandOffToMaster(conversation_id, note))


class AgentBooking(agent_ports.Booking):
    """Agent → Tenancy и Booking: окна, заявки, записи клиента."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def free_slots(
        self, master_id: UUID, service_id: UUID, since: datetime | None, limit: int
    ) -> list[agent_ports.FreeSlot]:
        """Ближайшие окна."""
        slots = await self._mediator().send(
            ListFreeSlots(master_id, service_id=service_id, window_from=since, limit=limit)
        )
        return [agent_ports.FreeSlot(s.start, s.end, s.service_id) for s in slots]

    async def request(
        self, master_id: UUID, client_id: UUID, service_id: UUID, start: datetime
    ) -> agent_ports.AppointmentSnapshot:
        """Заявка или ``SlotUnavailableError``."""
        try:
            return await self._mediator().send(RequestAppointment(master_id, client_id, service_id, start))
        except (
            SlotUnavailableError,
            InvalidTimeSlot,
            tenancy_errors.ServiceNotFoundError,
            tenancy_errors.InvalidSlotWindowError,
        ) as error:
            raise agent_ports.SlotUnavailableError(str(error)) from error

    async def client_appointments(
        self, master_id: UUID, client_id: UUID
    ) -> list[agent_ports.AppointmentSnapshot]:
        """Будущие записи клиента."""
        return list(await self._mediator().send(ListClientAppointments(master_id, client_id)))

    async def cancel(self, appointment_id: UUID, client_id: UUID) -> agent_ports.AppointmentSnapshot:
        """Отмена своей записи или ``ChangeRefusedError``."""
        try:
            return await self._mediator().send(CancelAppointment(appointment_id, client_id))
        except (AppointmentNotFoundError, ChangeDeadlinePassed, AppointmentClosed) as error:
            raise agent_ports.ChangeRefusedError(str(error)) from error


class AgentCabinet(agent_ports.Cabinet):
    """Agent (кабинет) → Booking, Tenancy, Conversations: действия от имени мастера."""

    _REFUSED = (
        AppointmentNotFoundError,
        AppointmentNotPending,
        AppointmentClosed,
        RequestExpired,
    )

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def day(self, master_id: UUID, day: date) -> Mapping[str, Any]:
        """График дня."""
        return await self._mediator().send(GetDaySchedule(master_id, day))

    async def clients(self, master_id: UUID, query: str) -> list[agent_ports.ClientBrief]:
        """Клиенты — по перепискам мастера (поиск списка чатов)."""
        inbox = await self._mediator().send(ListInbox(master_id, "all", query or None))
        return [
            agent_ports.ClientBrief(c.client_id, c.id, c.display_name, c.phone_masked, c.visit_number)
            for c in inbox.items
        ]

    async def book(
        self, master_id: UUID, client_id: UUID, service_id: UUID, start: datetime
    ) -> agent_ports.AppointmentSnapshot:
        """Заявка от имени мастера и сразу подтверждение."""
        try:
            requested = await self._mediator().send(
                RequestAppointment(master_id, client_id, service_id, start)
            )
        except (
            SlotUnavailableError,
            InvalidTimeSlot,
            tenancy_errors.ServiceNotFoundError,
            tenancy_errors.InvalidSlotWindowError,
        ) as error:
            raise agent_ports.SlotUnavailableError(str(error)) from error
        return await self.confirm(master_id, UUID(str(requested["id"])))

    async def confirm(self, master_id: UUID, appointment_id: UUID) -> agent_ports.AppointmentSnapshot:
        """Подтверждение заявки."""
        try:
            return await self._mediator().send(ConfirmAppointment(appointment_id, master_id))
        except self._REFUSED as error:
            raise agent_ports.ChangeRefusedError(str(error)) from error

    async def decline(
        self, master_id: UUID, appointment_id: UUID, *, offer_alternatives: bool
    ) -> agent_ports.AppointmentSnapshot:
        """Отклонение заявки."""
        try:
            return await self._mediator().send(
                DeclineAppointment(appointment_id, master_id, offer_alternatives=offer_alternatives)
            )
        except self._REFUSED as error:
            raise agent_ports.ChangeRefusedError(str(error)) from error

    async def cancel(
        self, master_id: UUID, appointment_id: UUID, *, offer_alternatives: bool
    ) -> agent_ports.AppointmentSnapshot:
        """Отмена мастером."""
        try:
            return await self._mediator().send(
                CancelAppointmentByMaster(appointment_id, master_id, offer_alternatives=offer_alternatives)
            )
        except self._REFUSED as error:
            raise agent_ports.ChangeRefusedError(str(error)) from error

    async def set_day_off(self, master_id: UUID, day: date, *, off: bool) -> bool:
        """Закрыть или открыть дату."""
        return await self._mediator().send(ChangeDayOff(master_id, day, off))

    async def message_client(self, master_id: UUID, client_id: UUID, text: str) -> None:
        """Сообщение клиенту от имени администратора."""
        try:
            await self._mediator().send(PostOnMasterBehalf(master_id, client_id, text))
        except ConversationNotFoundError as error:
            raise agent_ports.ClientNotFoundError() from error

    async def draft_broadcast(self, master_id: UUID, text: str) -> agent_ports.BroadcastDraft:
        """Черновик рассылки от агента."""
        try:
            broadcast_id = await self._mediator().send(DraftBroadcast(master_id, text, by_agent=True))
        except InvalidBroadcast as error:
            raise agent_ports.ChangeRefusedError(str(error)) from error
        view = await self._mediator().send(GetBroadcast(master_id, broadcast_id))
        return agent_ports.BroadcastDraft(broadcast_id, view.recipients)


class AgentClientBook(agent_ports.ClientBook):
    """Agent → Clientbook: заметки о клиенте и его имя у мастера."""

    _REFUSED = (
        clientbook_domain.InvalidClientName,
        clientbook_domain.InvalidClientNote,
        clientbook_domain.ClientNotesLimit,
    )

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def notes(self, master_id: UUID, client_id: UUID) -> list[agent_ports.ClientNoteBrief]:
        """Заметки, свежие сверху."""
        found = await self._mediator().send(ListClientNotes(master_id, client_id))
        return [agent_ports.ClientNoteBrief(n.text, n.author == "agent") for n in found]

    async def add_note(self, master_id: UUID, client_id: UUID, text: str) -> None:
        """Заметка ИИ-администратора."""
        try:
            await self._mediator().send(AddClientNote(master_id, client_id, text, by_agent=True))
        except clientbook_errors.ClientNotFoundError as error:
            raise agent_ports.ClientNotFoundError() from error
        except self._REFUSED as error:
            raise agent_ports.NoteRefusedError(str(error)) from error

    async def rename(self, master_id: UUID, client_id: UUID, name: str | None) -> None:
        """Имя у мастера."""
        try:
            await self._mediator().send(RenameClient(master_id, client_id, name))
        except clientbook_errors.ClientNotFoundError as error:
            raise agent_ports.ClientNotFoundError() from error
        except self._REFUSED as error:
            raise agent_ports.NoteRefusedError(str(error)) from error

    async def card(self, master_id: UUID, client_id: UUID) -> Mapping[str, Any] | None:
        """Карточка коротко — для модели."""
        try:
            card = await self._mediator().send(GetClientCard(master_id, client_id))
        except clientbook_errors.ClientNotFoundError:
            return None
        row = card.row

        def visit(v: Any) -> dict[str, Any]:
            return {"status": v.status, "start": v.start.isoformat(), "service": v.service_title}

        return {
            "client_id": str(row.client_id),
            "name": row.display_name,
            "phone": row.phone_masked,
            "visits": row.visits,
            "cancelled": card.cancelled,
            "last_visit": None if row.last_visit_at is None else row.last_visit_at.isoformat(),
            "upcoming": [visit(v) for v in card.upcoming],
            "recent": [visit(v) for v in card.history[:5]],
            "notes": [
                {"text": n.text, "by": "ИИ-администратор" if n.author == "agent" else "мастер"}
                for n in card.notes
            ],
        }


class NotificationsDirectory(notification_ports.Directory):
    """Notifications → Tenancy и Conversations: имена для текстов уведомлений."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def master(self, master_id: UUID) -> notification_ports.MasterCard | None:
        """Мастер (и черновик)."""
        try:
            page = await self._mediator().send(GetMasterPage(master_id, published_only=False))
        except tenancy_errors.MasterNotFoundError:
            return None
        return notification_ports.MasterCard(page.name_nominative, page.timezone)

    async def master_by_slug(self, slug: str) -> UUID | None:
        """Мастер по адресу страницы."""
        return await self._mediator().send(FindMasterId(slug))

    async def client_name(self, master_id: UUID, conversation_id: UUID) -> str | None:
        """Клиент глазами мастера."""
        try:
            summary = await self._mediator().send(GetConversationSummary(master_id, conversation_id))
        except ConversationNotFoundError:
            return None
        return str(summary.display_name)


class AdminPlatform(admin_ports.Platform):
    """Admin → Tenancy, Agent, Identity: изменения от имени хозяина сервиса."""

    def __init__(self, mediator: MediatorProvider) -> None:
        """Получить медиатор (лениво)."""
        self._mediator = mediator

    async def register_master(self, draft: admin_ports.MasterDraft) -> UUID:
        """Регистрация (черновик), специализация, владелец."""
        mediator = self._mediator()
        master_id: UUID = await mediator.send(
            RegisterMaster(
                draft.slug,
                draft.display_name,
                draft.name_nominative,
                draft.name_genitive,
                draft.name_dative,
                draft.timezone,
            )
        )
        if draft.specialty.strip():
            await mediator.send(
                UpdateMasterProfile(
                    master_id=master_id,
                    display_name=draft.display_name,
                    name_nominative=draft.name_nominative,
                    name_genitive=draft.name_genitive,
                    name_dative=draft.name_dative,
                    specialty=draft.specialty.strip(),
                    address="",
                    about="",
                    timezone=draft.timezone,
                )
            )
        if draft.owner_phone:
            await mediator.send(AssignOwner(draft.slug, draft.owner_phone))
        return master_id

    async def set_owner(self, master_id: UUID, phone: str) -> None:
        """Владелец по адресу страницы."""
        mediator = self._mediator()
        settings = await mediator.send(GetMasterSettings(master_id))
        await mediator.send(AssignOwner(settings.page.slug, phone))

    async def set_published(self, master_id: UUID, published: bool) -> None:
        """Публикация по правилам Tenancy."""
        command = PublishMaster(master_id) if published else UnpublishMaster(master_id)
        await self._mediator().send(command)

    async def set_agent(self, master_id: UUID, enabled: bool) -> None:
        """Агент мастера (профиль Hermes должен быть подключён)."""
        await self._mediator().send(SetAgentEnabled(master_id, enabled))

    async def set_client_blocked(self, client_id: UUID, blocked: bool, reason: str | None) -> None:
        """Блокировка в Identity."""
        await self._mediator().send(SetAccountBlocked(client_id, blocked, reason))

    async def set_broadcasts(self, master_id: UUID, allowed: bool) -> None:
        """Запрет рассылок — в Conversations."""
        await self._mediator().send(SetBroadcastsAllowed(master_id, allowed))


def admin_master_settings(mediator: MediatorProvider) -> Callable[[UUID], Any]:
    """Настройки страницы мастера в форме контракта ``MasterSettings`` (для отчётов панели)."""

    async def read(master_id: UUID) -> dict[str, Any] | None:
        try:
            view = await mediator().send(GetMasterSettings(master_id))
        except tenancy_errors.MasterNotFoundError:
            return None
        body: dict[str, Any] = MasterSettingsResponse.of(view).model_dump(mode="json")
        return body

    return read
