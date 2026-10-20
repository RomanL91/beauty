"""Инструменты ресепшна для MCP-сервера ``beauty-tools``.

Каждый вызов: токен профиля → мастер; тикет хода → тот же мастер, не истёк, роль
ресепшна. Клиент и переписка берутся из тикета, а не из аргументов модели — prompt
injection («запиши Оксану», «покажи чужие записи») не расширяет доступ.
Результаты — короткие словари: модель читает их как текст.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.agent.application.access import ToolAccess
from beauty.contexts.agent.application.playbook import load_playbook
from beauty.contexts.agent.application.ports import (
    Booking,
    ChangeRefusedError,
    ClientBook,
    ClientNotFoundError,
    Conversations,
    MasterBriefs,
    NoteRefusedError,
    ServiceBrief,
    SlotUnavailableError,
)
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.errors import InvalidTicket
from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.shared.domain.clock import Clock

logger = logging.getLogger(__name__)

MAX_SLOTS = 8
MAX_LOAD_DAYS = 3
SCAN_SLOTS = 100
"""Сколько окон просмотреть, когда модель ограничила время дня (``after``/``before``)."""


class SlotLookup:
    """Свободные окна услуги для модели (общий инструмент ресепшна и кабинета).

    Рядом с окнами — опыт мастера об этой услуге и загрузка дней: решение «какие окна
    предложить» модель принимает, глядя на всё сразу, а не вспоминая инструкции.
    """

    def __init__(
        self, masters: MasterBriefs, booking: Booking, uow_factory: Callable[[], AgentUnitOfWork]
    ) -> None:
        """Получить зависимости."""
        self._masters = masters
        self._booking = booking
        self._uow_factory = uow_factory

    async def find(
        self,
        master_id: UUID,
        service_id: str,
        date: str | None,
        after: str | None = None,
        before: str | None = None,
    ) -> dict[str, Any]:
        """Ближайшие окна услуги (с даты ``YYYY-MM-DD``; ``after``/``before`` — ``HH:MM`` дня)."""
        master = await self._masters.brief(master_id)
        service = known_service(master.services if master else (), service_id)
        if master is None or service is None:
            return {"ok": False, "error": "Нет такой услуги — возьми service_id из инструкций"}
        zone = ZoneInfo(master.timezone)
        try:
            since = (
                datetime.combine(datetime.fromisoformat(date).date(), time(), tzinfo=zone) if date else None
            )
            earliest = time.fromisoformat(after) if after else None
            latest = time.fromisoformat(before) if before else None
        except ValueError:
            return {"ok": False, "error": "Дата — YYYY-MM-DD, время after/before — HH:MM"}
        scan = MAX_SLOTS if earliest is None and latest is None else SCAN_SLOTS
        found = await self._booking.free_slots(master.id, service, since, scan)
        slots = [
            s
            for s in found
            if (earliest is None or s.start.astimezone(zone).time() >= earliest)
            and (latest is None or s.end.astimezone(zone).time() <= latest)
        ][:MAX_SLOTS]
        days = sorted({s.start.astimezone(zone).date() for s in slots})[:MAX_LOAD_DAYS]
        playbook = await load_playbook(self._uow_factory, master)
        notes = [p.text for p in playbook.about(service)] + [p.text for p in playbook.general()]
        return {
            "ok": True,
            "service_id": str(service),
            **({"master_experience": notes} if notes else {}),
            "slots": [{"start": s.start.isoformat(), "end": s.end.isoformat()} for s in slots],
            "day_load": [
                {
                    "date": day.isoformat(),
                    "booked": [
                        {
                            "start": f"{b.start.astimezone(zone):%H:%M}",
                            "end": f"{b.end.astimezone(zone):%H:%M}",
                            "service": b.service,
                            "confirmed": b.status == "confirmed",
                        }
                        for b in await self._booking.day_load(master.id, day)
                    ],
                }
                for day in days
            ],
        }


def known_service(services: Iterable[ServiceBrief], service_id: str) -> UUID | None:
    """Услуга мастера по строке id от модели (чужая или мусор — ``None``)."""
    try:
        wanted = UUID(service_id)
    except (ValueError, TypeError):
        return None
    return wanted if any(s.id == wanted for s in services) else None


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
        clients: ClientBook,
        clock: Clock,
    ) -> None:
        """Получить зависимости."""
        self._uow_factory = uow_factory
        self._access = ToolAccess(uow_factory, clock)
        self._slots = SlotLookup(masters, booking, uow_factory)
        self._masters = masters
        self._booking = booking
        self._conversations = conversations
        self._clients = clients

    async def authorize(self, token: str, profile_header: str | None, ticket_id: str) -> ToolCaller:
        """Проверить токен профиля ресепшна, заголовок профиля и тикет хода."""
        grant = await self._access.grant(token, profile_header, ticket_id, AgentFace.FRONT_DESK)
        if grant.conversation_id is None or grant.client_id is None:
            raise InvalidTicket()
        return ToolCaller(grant.master_id, grant.ticket_id, grant.conversation_id, grant.client_id)

    async def find_free_slots(
        self,
        caller: ToolCaller,
        service_id: str,
        date: str | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> dict[str, Any]:
        """Ближайшие окна услуги (с даты ``YYYY-MM-DD``, в пределах ``after``–``before`` дня)."""
        return await self._slots.find(caller.master_id, service_id, date, after, before)

    async def book_appointment(self, caller: ToolCaller, service_id: str, start: str) -> dict[str, Any]:
        """Заявка клиента тикета на окно (мастер подтвердит)."""
        master = await self._masters.brief(caller.master_id)
        service = known_service(master.services if master else (), service_id)
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
        note = f"Заявка отправлена, {master.name} подтвердит. Карточка уже в чате у клиента."
        playbook = await load_playbook(self._uow_factory, master)
        if playbook.auto_confirm:
            try:
                appointment = await self._booking.confirm(master.id, UUID(str(appointment["id"])))
                note = "Записал: запись подтверждена, карточка в чате у клиента."
            except ChangeRefusedError:
                logger.warning("Ресепшн не подтвердил заявку %s сам", appointment["id"])
        return {
            "ok": True,
            "appointment_id": appointment["id"],
            "status": appointment["status"],
            "start": appointment["start"],
            "note": note,
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

    async def remember_client(self, caller: ToolCaller, note: str) -> dict[str, Any]:
        """Заметка о клиенте тикета в картотеку мастера."""
        try:
            await self._clients.add_note(caller.master_id, caller.client_id, note)
        except (ClientNotFoundError, NoteRefusedError) as error:
            return {"ok": False, "error": str(error) or "Заметку сохранить не получилось"}
        return {"ok": True, "note": "Сохранено в карточке клиента; клиенту об этом говорить не нужно"}

    async def set_client_name(self, caller: ToolCaller, name: str) -> dict[str, Any]:
        """Имя клиента тикета в картотеке мастера — как клиент сам просит к нему обращаться."""
        cleaned = " ".join(name.split())
        if not cleaned:
            return {"ok": False, "error": "Нужно имя, как клиент его назвал"}
        try:
            await self._clients.rename(caller.master_id, caller.client_id, cleaned)
        except (ClientNotFoundError, NoteRefusedError) as error:
            return {"ok": False, "error": str(error) or "Имя сохранить не получилось"}
        return {"ok": True, "name": cleaned, "note": "Карточка подписана; обращайся к клиенту так"}

    async def handoff_to_master(self, caller: ToolCaller, summary: str) -> dict[str, Any]:
        """Передать диалог мастеру с кратким пересказом."""
        await self._conversations.hand_off(caller.conversation_id, f"Агент передал вам: {summary}")
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get(caller.ticket_id)
            if ticket is not None:
                ticket.hand_off()
                await uow.commit()
        return {"ok": True, "note": "Мастер увидит вопрос; скажи клиенту, что мастер ответит здесь"}
