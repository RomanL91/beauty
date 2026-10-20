"""Инструменты кабинета (MCP ``/office/mcp``): агент действует от имени мастера.

Доступ — токен профиля кабинета и тикет хода кабинета (``ToolAccess``). Мастер берётся из
тикета: агент кабинета видит и меняет только записи, клиентов и график своего мастера.
Результаты — короткие словари: модель читает их как текст.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.agent.application.access import Grant, ToolAccess
from beauty.contexts.agent.application.ports import (
    Booking,
    Cabinet,
    ChangeRefusedError,
    ClientBook,
    ClientNotFoundError,
    MasterBriefs,
    NoteRefusedError,
    SlotUnavailableError,
)
from beauty.contexts.agent.application.toolkit import SlotLookup, known_service
from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.domain.office import OfficeMessage, choice
from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

MAX_CLIENTS = 5
MAX_MESSAGE = 1000

type Result = dict[str, Any]


def _refused(error: Exception, fallback: str) -> Result:
    return {"ok": False, "error": str(error) or fallback}


def _appointment(snapshot: Mapping[str, Any]) -> Result:
    """Запись коротко: id, статус, время, услуга, клиент."""
    service = snapshot.get("service") or {}
    client = snapshot.get("client") or {}
    return {
        "appointment_id": snapshot.get("id"),
        "status": snapshot.get("status"),
        "start": snapshot.get("start"),
        "end": snapshot.get("end"),
        "service": service.get("title"),
        "client": client.get("display_name"),
        "client_id": client.get("id"),
    }


class OfficeToolkit:
    """Инструменты кабинета поверх соседних контекстов."""

    def __init__(
        self,
        uow_factory: Callable[[], AgentUnitOfWork],
        masters: MasterBriefs,
        booking: Booking,
        cabinet: Cabinet,
        clients: ClientBook,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        """Получить зависимости."""
        self._uow_factory = uow_factory
        self._access = ToolAccess(uow_factory, clock)
        self._slots = SlotLookup(masters, booking)
        self._masters = masters
        self._cabinet = cabinet
        self._clients = clients
        self._clock = clock
        self._ids = ids

    async def authorize(self, token: str, profile_header: str | None, ticket_id: str) -> Grant:
        """Проверить токен профиля кабинета, заголовок профиля и тикет хода."""
        return await self._access.grant(token, profile_header, ticket_id, AgentFace.BACK_OFFICE)

    async def day_schedule(self, caller: Grant, day: str | None) -> Result:
        """Записи, заявки и свободные окна дня."""
        target = await self._date(caller.master_id, day)
        if target is None:
            return {"ok": False, "error": "Дата — в формате YYYY-MM-DD"}
        schedule = await self._cabinet.day(caller.master_id, target)
        items: list[Result] = []
        for item in schedule.get("items", []):
            if item.get("kind") == "appointment":
                items.append({"kind": "appointment", **_appointment(item["appointment"])})
            else:
                items.append({"kind": item.get("kind"), "start": item.get("start"), "end": item.get("end")})
        return {
            "ok": True,
            "date": target.isoformat(),
            "day_off": schedule.get("day_off", False),
            "items": items,
        }

    async def find_free_slots(self, caller: Grant, service_id: str, day: str | None) -> Result:
        """Свободные окна услуги."""
        return await self._slots.find(caller.master_id, service_id, day)

    async def find_clients(self, caller: Grant, query: str) -> Result:
        """Клиенты мастера по имени или цифрам телефона."""
        found = await self._cabinet.clients(caller.master_id, query.strip())
        return {
            "ok": True,
            "clients": [
                {
                    "client_id": str(c.client_id),
                    "name": c.display_name,
                    "phone": c.phone_masked,
                    "visits": c.visit_number - 1,
                }
                for c in found[:MAX_CLIENTS]
            ],
        }

    async def book_client(self, caller: Grant, client_id: str, service_id: str, start: str) -> Result:
        """Записать клиента от имени мастера (сразу подтверждено)."""
        master = await self._masters.brief(caller.master_id)
        service = known_service(master.services if master else (), service_id)
        client = _uuid(client_id)
        if master is None or service is None or client is None:
            return {"ok": False, "error": "Нужны client_id из find_clients и service_id из инструкций"}
        try:
            moment = datetime.fromisoformat(start)
        except ValueError:
            return {"ok": False, "error": "start — время окна из find_free_slots (ISO 8601)"}
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=ZoneInfo(master.timezone))
        try:
            booked = await self._cabinet.book(caller.master_id, client, service, moment)
        except SlotUnavailableError:
            return {"ok": False, "error": "Это время занято или вне графика — возьми окно из find_free_slots"}
        except ChangeRefusedError as error:
            return _refused(error, "Записать не получилось")
        return {"ok": True, **_appointment(booked)}

    async def confirm_request(self, caller: Grant, appointment_id: str) -> Result:
        """Подтвердить заявку."""
        return await self._decide(appointment_id, lambda a: self._cabinet.confirm(caller.master_id, a))

    async def decline_request(self, caller: Grant, appointment_id: str, offer_alternatives: bool) -> Result:
        """Отклонить заявку (клиенту — другие окна, если ``offer_alternatives``)."""
        return await self._decide(
            appointment_id,
            lambda a: self._cabinet.decline(caller.master_id, a, offer_alternatives=offer_alternatives),
        )

    async def cancel_appointment(
        self, caller: Grant, appointment_id: str, offer_alternatives: bool
    ) -> Result:
        """Отменить заявку или запись."""
        return await self._decide(
            appointment_id,
            lambda a: self._cabinet.cancel(caller.master_id, a, offer_alternatives=offer_alternatives),
        )

    async def set_day_off(self, caller: Grant, day: str, off: bool) -> Result:
        """Закрыть или открыть дату."""
        target = await self._date(caller.master_id, day)
        if target is None:
            return {"ok": False, "error": "Дата — в формате YYYY-MM-DD"}
        is_off = await self._cabinet.set_day_off(caller.master_id, target, off=off)
        if is_off != off:
            return {"ok": False, "error": "Прошедшую дату изменить нельзя"}
        note = "Записи этого дня не отменены — отмени их отдельно, если нужно." if off else ""
        return {"ok": True, "date": target.isoformat(), "day_off": is_off, "note": note}

    async def message_client(self, caller: Grant, client_id: str, text: str) -> Result:
        """Написать клиенту от имени администратора."""
        client = _uuid(client_id)
        body = text.strip()
        if client is None or not body:
            return {"ok": False, "error": "Нужны client_id из find_clients и текст"}
        try:
            await self._cabinet.message_client(caller.master_id, client, body[:MAX_MESSAGE])
        except ClientNotFoundError:
            return {"ok": False, "error": "С этим клиентом ещё нет переписки"}
        return {"ok": True, "note": "Сообщение в чате клиента"}

    async def client_card(self, caller: Grant, client_id: str) -> Result:
        """Карточка клиента: имя, визиты, ближайшие записи, заметки."""
        client = _uuid(client_id)
        card = None if client is None else await self._clients.card(caller.master_id, client)
        if card is None:
            return {"ok": False, "error": "Нужен client_id из find_clients"}
        return {"ok": True, **card}

    async def add_client_note(self, caller: Grant, client_id: str, text: str) -> Result:
        """Заметка о клиенте в картотеку мастера."""
        client = _uuid(client_id)
        if client is None:
            return {"ok": False, "error": "Нужен client_id из find_clients"}
        try:
            await self._clients.add_note(caller.master_id, client, text)
        except ClientNotFoundError:
            return {"ok": False, "error": "У мастера нет такого клиента"}
        except NoteRefusedError as error:
            return _refused(error, "Заметку сохранить не получилось")
        return {"ok": True, "note": "Заметка в карточке клиента"}

    async def rename_client(self, caller: Grant, client_id: str, name: str | None) -> Result:
        """Имя клиента у мастера (пусто — подпись по телефону)."""
        client = _uuid(client_id)
        if client is None:
            return {"ok": False, "error": "Нужен client_id из find_clients"}
        try:
            await self._clients.rename(caller.master_id, client, name)
        except ClientNotFoundError:
            return {"ok": False, "error": "У мастера нет такого клиента"}
        except NoteRefusedError as error:
            return _refused(error, "Имя сохранить не получилось")
        return {"ok": True, "name": (name or "").strip() or None, "note": "Имя видно в чатах и графике"}

    async def ask_master(
        self, caller: Grant, question: str, options: list[str], detail: str | None
    ) -> Result:
        """Карточка выбора мастеру; ход на этом заканчивается."""
        try:
            content = choice(question, options, detail)
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get(caller.ticket_id)
            uow.office.add(
                OfficeMessage.from_agent(
                    message_id=self._ids.new(),
                    master_id=caller.master_id,
                    content=content,
                    now=self._clock.now(),
                )
            )
            if ticket is not None:
                ticket.ask_master()
            await uow.commit()
        return {"ok": True, "note": "Вопрос у мастера. Закончи ход — ответ придёт следующим сообщением."}

    async def _decide(self, appointment_id: str, action: Callable[[UUID], Any]) -> Result:
        target = _uuid(appointment_id)
        if target is None:
            return {"ok": False, "error": "appointment_id — из day_schedule"}
        try:
            snapshot = await action(target)
        except ChangeRefusedError as error:
            return _refused(error, "Эту запись изменить нельзя")
        return {"ok": True, **_appointment(snapshot)}

    async def _date(self, master_id: UUID, raw: str | None) -> date | None:
        if raw:
            try:
                return date.fromisoformat(raw.strip())
            except ValueError:
                return None
        master = await self._masters.brief(master_id)
        zone = ZoneInfo(master.timezone) if master is not None else None
        return self._clock.now().astimezone(zone).date()


def _uuid(raw: str) -> UUID | None:
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return None
