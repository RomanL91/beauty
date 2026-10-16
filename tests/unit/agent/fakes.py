"""Двойники контекста Agent."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from beauty.contexts.agent.application.ports import (
    AgentRuntime,
    AppointmentSnapshot,
    Booking,
    ChangeRefusedError,
    ConversationInfo,
    Conversations,
    FreeSlot,
    MasterBrief,
    MasterBriefs,
    RunOutcome,
    RunRequest,
    ServiceBrief,
    SlotUnavailableError,
)
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.repositories import AgentProfileRepository, RunTicketRepository
from beauty.contexts.agent.domain.ticket import RunTicket
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


class _Profiles(AgentProfileRepository):
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def add(self, profile: AgentProfile) -> None:
        self._store.profiles[profile.id] = profile

    async def get(self, master_id: UUID) -> AgentProfile | None:
        return self._store.profiles.get(master_id)

    async def by_token(self, token: HashedSecret) -> AgentProfile | None:
        return next((p for p in self._store.profiles.values() if p.mcp_token == token), None)


class _Tickets(RunTicketRepository):
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def add(self, ticket: RunTicket) -> None:
        self._store.tickets[ticket.id] = ticket

    async def get(self, ticket_id: str) -> RunTicket | None:
        return self._store.tickets.get(ticket_id)


class InMemoryAgentUnitOfWork(AgentUnitOfWork):
    """Unit of Work в памяти."""

    def __init__(self, store: AgentStore) -> None:
        """Связать с хранилищем."""
        self.profiles = _Profiles(store)
        self.tickets = _Tickets(store)

    async def commit(self) -> None:
        """Ничего не нужно."""

    async def rollback(self) -> None:
        """Ничего не нужно."""


class Masters(MasterBriefs):
    """Один мастер."""

    async def brief(self, master_id: UUID) -> MasterBrief | None:
        """Мастер или ``None``."""
        return BRIEF if master_id == MASTER else None


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
