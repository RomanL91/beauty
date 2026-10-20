"""Двойники контекста Agent."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from beauty.contexts.agent.application.ports import (
    AgentRuntime,
    AppointmentSnapshot,
    Booking,
    Cabinet,
    ChangeRefusedError,
    ClientBook,
    ClientBrief,
    ClientNoteBrief,
    ClientNotFoundError,
    ConversationInfo,
    Conversations,
    FreeSlot,
    MasterBrief,
    MasterBriefs,
    NoteRefusedError,
    RunOutcome,
    RunRequest,
    ServiceBrief,
    SlotUnavailableError,
)
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.office import OfficeMessage
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.repositories import (
    AgentProfileRepository,
    AgentRunRepository,
    OfficeMessageRepository,
    RunTicketRepository,
)
from beauty.contexts.agent.domain.run import AgentRun
from beauty.contexts.agent.domain.ticket import AgentFace, RunTicket
from beauty.shared.domain.secrets import HashedSecret

MASTER = UUID(int=1)
CLIENT = UUID(int=2)
CONVERSATION = UUID(int=3)
SERVICE = ServiceBrief(UUID(int=4), "Массаж спины", 60, 1_200_000)
BRIEF = MasterBrief(MASTER, "Алиса", "Массаж", "Абая 1", "Asia/Almaty", (SERVICE,), 2, 12)


class AgentStore:
    """Профили и тикеты, переживающие Unit of Work."""

    def __init__(self) -> None:
        """Пусто."""
        self.profiles: dict[UUID, AgentProfile] = {}
        self.tickets: dict[str, RunTicket] = {}
        self.office: dict[UUID, OfficeMessage] = {}
        self.runs: list[AgentRun] = []
        self.events: list[Any] = []


class _Profiles(AgentProfileRepository):
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def add(self, profile: AgentProfile) -> None:
        self._store.profiles[profile.id] = profile

    async def get(self, master_id: UUID) -> AgentProfile | None:
        return self._store.profiles.get(master_id)

    async def by_token(self, token: HashedSecret) -> AgentProfile | None:
        return next((p for p in self._store.profiles.values() if p.face_of(token) is not None), None)


class _Tickets(RunTicketRepository):
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def add(self, ticket: RunTicket) -> None:
        self._store.tickets[ticket.id] = ticket

    async def get(self, ticket_id: str) -> RunTicket | None:
        return self._store.tickets.get(ticket_id)

    async def latest(
        self, master_id: UUID, face: AgentFace, conversation_id: UUID | None
    ) -> RunTicket | None:
        thread = [
            t
            for t in self._store.tickets.values()
            if (t.master_id, t.face, t.conversation_id) == (master_id, face, conversation_id)
        ]
        return max(thread, key=lambda t: t.created_at, default=None)


class _Office(OfficeMessageRepository):
    def __init__(self, store: AgentStore, seen: list[OfficeMessage]) -> None:
        self._store = store
        self._seen = seen

    def add(self, message: OfficeMessage) -> None:
        self._store.office[message.id] = message
        self._seen.append(message)

    async def get(self, master_id: UUID, message_id: UUID) -> OfficeMessage | None:
        found = self._store.office.get(message_id)
        if found is not None and found.master_id == master_id:
            self._seen.append(found)
            return found
        return None

    async def by_client_id(self, master_id: UUID, client_message_id: UUID) -> OfficeMessage | None:
        return next(
            (
                m
                for m in self._store.office.values()
                if m.master_id == master_id and m.client_message_id == client_message_id
            ),
            None,
        )

    async def page(
        self, master_id: UUID, before: UUID | None, limit: int
    ) -> tuple[list[OfficeMessage], bool]:
        mine = sorted(
            (
                m
                for m in self._store.office.values()
                if m.master_id == master_id and (before is None or m.id < before)
            ),
            key=lambda m: m.id,
        )
        return mine[-limit:], len(mine) > limit


class _Runs(AgentRunRepository):
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def add(self, run: AgentRun) -> None:
        self._store.runs.append(run)


class InMemoryAgentUnitOfWork(AgentUnitOfWork):
    """Unit of Work в памяти; события агрегатов ленты — в ``store.events`` при коммите."""

    def __init__(self, store: AgentStore) -> None:
        """Связать с хранилищем."""
        self._store = store
        self._seen: list[OfficeMessage] = []
        self.profiles = _Profiles(store)
        self.tickets = _Tickets(store)
        self.office = _Office(store, self._seen)
        self.runs = _Runs(store)

    async def commit(self) -> None:
        """Собрать события."""
        for message in self._seen:
            self._store.events.extend(message.pull_events())

    async def rollback(self) -> None:
        """Ничего не нужно."""


class Masters(MasterBriefs):
    """Один мастер; ``current`` — его страница сейчас (тест может её править)."""

    def __init__(self, current: MasterBrief = BRIEF) -> None:
        """Страница мастера."""
        self.current = current

    async def brief(self, master_id: UUID) -> MasterBrief | None:
        """Мастер или ``None``."""
        return self.current if master_id == MASTER else None


class RecordingConversations(Conversations):
    """Запоминает ответы и передачи."""

    def __init__(self, handler: str = "agent") -> None:
        """Обработчик переписки."""
        self.handler = handler
        self.replies: list[tuple[str, bool]] = []
        self.handoffs: list[str] = []

    async def state(self, conversation_id: UUID) -> ConversationInfo:
        """Переписка Алисы с клиентом."""
        return ConversationInfo(MASTER, CLIENT, "Новый клиент · …89 67", self.handler)

    async def reply(self, conversation_id: UUID, text: str, *, resolve_question: bool) -> bool:
        """Запомнить ответ."""
        self.replies.append((text, resolve_question))
        return True

    async def hand_off(self, conversation_id: UUID, note: str) -> None:
        """Запомнить передачу."""
        self.handoffs.append(note)


class ScriptedRuntime(AgentRuntime):
    """Runtime, исполняющий сценарий хода (как Hermes — с вызовами инструментов)."""

    def __init__(self, script: Callable[[RunRequest], Any] | None = None, enabled: bool = True) -> None:
        """``script(request)`` → текст ответа или ``RunOutcome``."""
        self._script = script
        self._enabled = enabled
        self.requests: list[RunRequest] = []

    @property
    def enabled(self) -> bool:
        """Включён ли."""
        return self._enabled

    async def run(self, request: RunRequest) -> RunOutcome:
        """Выполнить сценарий."""
        self.requests.append(request)
        result = await self._script(request) if self._script else "Здравствуйте!"
        return result if isinstance(result, RunOutcome) else RunOutcome("completed", str(result))


class FakeBooking(Booking):
    """Окна по часу с 10:00 завтра; занятое время задаётся множеством."""

    def __init__(self, now: datetime) -> None:
        """Начать с завтрашних окон."""
        base = (now + timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)
        self.slots = [base + timedelta(hours=h) for h in range(4)]
        self.taken: set[datetime] = set()
        self.requests: list[tuple[UUID, UUID, datetime]] = []
        self.cancelled: list[UUID] = []

    async def free_slots(
        self, master_id: UUID, service_id: UUID, since: datetime | None, limit: int
    ) -> list[FreeSlot]:
        """Свободные окна."""
        return [
            FreeSlot(s, s + timedelta(hours=1), service_id)
            for s in self.slots
            if s not in self.taken and (since is None or s >= since)
        ][:limit]

    async def request(
        self, master_id: UUID, client_id: UUID, service_id: UUID, start: datetime
    ) -> AppointmentSnapshot:
        """Заявка или занято."""
        if start in self.taken or start not in self.slots:
            raise SlotUnavailableError()
        self.taken.add(start)
        self.requests.append((client_id, service_id, start))
        return {"id": str(UUID(int=99)), "status": "requested", "start": start.isoformat()}

    async def client_appointments(self, master_id: UUID, client_id: UUID) -> list[AppointmentSnapshot]:
        """Заявки клиента."""
        return [
            {
                "id": str(UUID(int=99)),
                "status": "requested",
                "service": {"title": "Массаж спины"},
                "start": s.isoformat(),
            }
            for c, _, s in self.requests
            if c == client_id
        ]

    async def cancel(self, appointment_id: UUID, client_id: UUID) -> AppointmentSnapshot:
        """Отмена только своей заявки."""
        if client_id != CLIENT:
            raise ChangeRefusedError("Запись не найдена")
        self.cancelled.append(appointment_id)
        return {"id": str(appointment_id), "status": "cancelled"}


class FakeCabinet(Cabinet):
    """Кабинет мастера в памяти: записывает действия."""

    def __init__(self) -> None:
        """Пусто."""
        self.actions: list[tuple[str, Any]] = []
        self.days_off: set[date] = set()

    async def day(self, master_id: UUID, day: date) -> Mapping[str, Any]:
        """Одна запись и одно окно."""
        return {
            "date": day.isoformat(),
            "day_off": day in self.days_off,
            "items": [
                {
                    "kind": "appointment",
                    "appointment": {
                        "id": str(UUID(int=77)),
                        "status": "confirmed",
                        "start": f"{day}T12:00:00+05:00",
                        "end": f"{day}T13:00:00+05:00",
                        "service": {"title": "Массаж спины"},
                        "client": {"id": str(CLIENT), "display_name": "Дарья К."},
                    },
                    "conversation_id": str(CONVERSATION),
                },
                {"kind": "free", "start": f"{day}T14:00:00+05:00", "end": f"{day}T15:00:00+05:00"},
            ],
        }

    async def clients(self, master_id: UUID, query: str) -> list[ClientBrief]:
        """Дарья находится по имени."""
        darya = ClientBrief(CLIENT, CONVERSATION, "Дарья К.", "+7 705 ••• 89 67", 3)
        return [darya] if "дар" in query.lower() else []

    async def book(
        self, master_id: UUID, client_id: UUID, service_id: UUID, start: datetime
    ) -> AppointmentSnapshot:
        """Запись."""
        self.actions.append(("book", (client_id, service_id, start)))
        return {"id": str(UUID(int=78)), "status": "confirmed", "start": start.isoformat()}

    async def confirm(self, master_id: UUID, appointment_id: UUID) -> AppointmentSnapshot:
        """Подтверждение."""
        self.actions.append(("confirm", appointment_id))
        return {"id": str(appointment_id), "status": "confirmed"}

    async def decline(
        self, master_id: UUID, appointment_id: UUID, *, offer_alternatives: bool
    ) -> AppointmentSnapshot:
        """Отклонение."""
        self.actions.append(("decline", (appointment_id, offer_alternatives)))
        return {"id": str(appointment_id), "status": "cancelled"}

    async def cancel(
        self, master_id: UUID, appointment_id: UUID, *, offer_alternatives: bool
    ) -> AppointmentSnapshot:
        """Отмена; чужая запись — отказ."""
        if appointment_id != UUID(int=77):
            raise ChangeRefusedError("Запись не найдена")
        self.actions.append(("cancel", (appointment_id, offer_alternatives)))
        return {"id": str(appointment_id), "status": "cancelled"}

    async def set_day_off(self, master_id: UUID, day: date, *, off: bool) -> bool:
        """Выходной."""
        (self.days_off.add if off else self.days_off.discard)(day)
        return day in self.days_off

    async def message_client(self, master_id: UUID, client_id: UUID, text: str) -> None:
        """Сообщение только Дарье."""
        if client_id != CLIENT:
            raise ClientNotFoundError()
        self.actions.append(("message", (client_id, text)))


class FakeClientBook(ClientBook):
    """Картотека в памяти: заметки и имена по клиентам; клиенты — ``known``."""

    def __init__(self, known: frozenset[UUID] = frozenset({CLIENT})) -> None:
        """Известные клиенты мастера."""
        self.known = known
        self.store: dict[UUID, list[ClientNoteBrief]] = {}
        self.names: dict[UUID, str | None] = {}

    async def notes(self, master_id: UUID, client_id: UUID) -> list[ClientNoteBrief]:
        """Свежие сверху."""
        return list(reversed(self.store.get(client_id, [])))

    def _check(self, client_id: UUID) -> None:
        if client_id not in self.known:
            raise ClientNotFoundError()

    async def add_note(self, master_id: UUID, client_id: UUID, text: str) -> None:
        """Заметка агента (пустая или длинная — отказ)."""
        self._check(client_id)
        if not text.strip() or len(text) > 500:
            raise NoteRefusedError("Заметка — от 1 до 500 символов")
        self.store.setdefault(client_id, []).append(ClientNoteBrief(text.strip(), True))

    async def rename(self, master_id: UUID, client_id: UUID, name: str | None) -> None:
        """Имя."""
        self._check(client_id)
        self.names[client_id] = (name or "").strip() or None

    async def card(self, master_id: UUID, client_id: UUID) -> Mapping[str, Any] | None:
        """Карточка коротко."""
        if client_id not in self.known:
            return None
        return {
            "client_id": str(client_id),
            "name": self.names.get(client_id) or "Новый клиент · …89 67",
            "notes": [{"text": n.text} for n in await self.notes(master_id, client_id)],
        }
