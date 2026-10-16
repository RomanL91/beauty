"""Инструменты ресепшна для MCP-сервера ``beauty-tools``.

Каждый вызов: токен профиля → мастер; тикет хода → тот же мастер, не истёк, роль
ресепшна. Клиент и переписка берутся из тикета, а не из аргументов модели — prompt
injection («запиши Оксану», «покажи чужие записи») не расширяет доступ.
Результаты — короткие словари: модель читает их как текст.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.agent.application.errors import UnknownProfileTokenError
from beauty.contexts.agent.application.ports import (
    Booking,
    ChangeRefusedError,
    Conversations,
    MasterBriefs,
    SlotUnavailableError,
)
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.errors import InvalidTicket
from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.secrets import HashedSecret

logger = logging.getLogger(__name__)

MAX_SLOTS = 8


@dataclass(frozen=True, slots=True)
class ToolCaller:
    """Кто вызывает инструмент: мастер профиля и данные тикета хода (без ORM-объектов)."""

    master_id: UUID
    ticket_id: str
    conversation_id: UUID
    client_id: UUID


class FrontDeskToolkit:
    """Инструменты ресепшна поверх соседних контекстов."""

    def __init__(
        self,
        uow_factory: Callable[[], AgentUnitOfWork],
        masters: MasterBriefs,
        booking: Booking,
        conversations: Conversations,
        clock: Clock,
    ) -> None:
        """Получить зависимости."""
        self._uow_factory = uow_factory
        self._masters = masters
        self._booking = booking
        self._conversations = conversations
        self._clock = clock

    async def authorize(self, token: str, profile_header: str | None, ticket_id: str) -> ToolCaller:
        """Проверить токен профиля, заголовок профиля и тикет хода."""
        async with self._uow_factory() as uow:
            profile = await uow.profiles.by_token(HashedSecret.of(token)) if token else None
            if profile is None or not profile.enabled:
                raise UnknownProfileTokenError()
            if profile_header is not None and profile_header != profile.profile_name:
                raise UnknownProfileTokenError("Заголовок профиля не совпадает с токеном")
            ticket = await uow.tickets.get(ticket_id.strip())
            if ticket is None:
                raise InvalidTicket()
            ticket.check(profile.master_id, AgentFace.FRONT_DESK, self._clock.now())
            return ToolCaller(profile.master_id, ticket.id, ticket.conversation_id, ticket.client_id)

    async def find_free_slots(
        self, caller: ToolCaller, service_id: str, date: str | None = None
    ) -> dict[str, Any]:
        """Ближайшие окна услуги (с даты ``YYYY-MM-DD`` в поясе мастера)."""
        master = await self._masters.brief(caller.master_id)
        service = self._service(master.services if master else (), service_id)
        if master is None or service is None:
            return {"ok": False, "error": "Нет такой услуги — возьми service_id из инструкций"}
        zone = ZoneInfo(master.timezone)
        since = None
        if date:
            try:
                since = datetime.combine(datetime.fromisoformat(date).date(), time(), tzinfo=zone)
            except ValueError:
                return {"ok": False, "error": "Дата — в формате YYYY-MM-DD"}
        slots = await self._booking.free_slots(master.id, service, since, MAX_SLOTS)
        return {
            "ok": True,
            "service_id": str(service),
            "slots": [{"start": s.start.isoformat(), "end": s.end.isoformat()} for s in slots],
        }

    async def book_appointment(self, caller: ToolCaller, service_id: str, start: str) -> dict[str, Any]:
        """Заявка клиента тикета на окно (мастер подтвердит)."""
        master = await self._masters.brief(caller.master_id)
        service = self._service(master.services if master else (), service_id)
        if master is None or service is None:
            return {"ok": False, "error": "Нет такой услуги — возьми service_id из инструкций"}
        try:
            moment = datetime.fromisoformat(start)
        except ValueError:
            return {"ok": False, "error": "start — время окна из find_free_slots (ISO 8601)"}
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=ZoneInfo(master.timezone))
        try:
            appointment = await self._booking.request(master.id, caller.client_id, service, moment)
        except SlotUnavailableError:
            return {
                "ok": False,
                "error": "Это окно уже недоступно — предложи клиенту другие из find_free_slots",
            }
        return {
            "ok": True,
            "appointment_id": appointment["id"],
            "status": appointment["status"],
            "start": appointment["start"],
            "note": f"Заявка отправлена, {master.name} подтвердит. Карточка уже в чате у клиента.",
        }

    async def my_appointments(self, caller: ToolCaller) -> dict[str, Any]:
        """Будущие заявки и записи клиента тикета."""
        found = await self._booking.client_appointments(caller.master_id, caller.client_id)
        return {
            "ok": True,
            "appointments": [
                {
                    "appointment_id": a["id"],
                    "status": a["status"],
                    "service": a["service"]["title"],
                    "start": a["start"],
                }
                for a in found
            ],
        }

    async def cancel_appointment(self, caller: ToolCaller, appointment_id: str) -> dict[str, Any]:
        """Отменить запись клиента тикета (только его собственную)."""
        try:
            cancelled = await self._booking.cancel(UUID(appointment_id), caller.client_id)
        except (ValueError, ChangeRefusedError) as error:
            return {"ok": False, "error": str(error) or "Эту запись отменить нельзя"}
        return {"ok": True, "status": cancelled["status"]}

    async def handoff_to_master(self, caller: ToolCaller, summary: str) -> dict[str, Any]:
        """Передать диалог мастеру с кратким пересказом."""
        await self._conversations.hand_off(caller.conversation_id, f"Агент передал вам: {summary}")
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get(caller.ticket_id)
            if ticket is not None:
                ticket.hand_off()
                await uow.commit()
        return {"ok": True, "note": "Мастер увидит вопрос; скажи клиенту, что мастер ответит здесь"}

    @staticmethod
    def _service(services: Any, service_id: str) -> UUID | None:
        try:
            wanted = UUID(service_id)
        except (ValueError, TypeError):
            return None
        return wanted if any(s.id == wanted for s in services) else None
