"""MCP-заглушка ``beauty-tools`` для спайка.

Повторяет контракт будущего MCP-сервера бэкенда, но поверх фейковых данных:

* аутентификация профиля — Bearer-токен из ``.env`` профиля (``BEAUTY_MCP_TOKEN``),
  сверка с заголовком ``X-Hermes-Profile`` (Hermes подставляет имя профиля сам);
* авторизация действия — capability-тикет запуска (``ticket``);
* каждый вызов пишется в ``calls.jsonl`` — по журналу харнесс проверяет изоляцию.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from spikes.hermes.fixtures import BUSY_SLOTS, CLIENTS, FREE_SLOTS, SERVICES, FakeClient
from spikes.hermes.registry import MasterRecord, MasterRegistry
from spikes.hermes.tickets import AgentFace, CapabilityTicket, InvalidTicketError, TicketCodec

PROFILE_HEADER = "x-hermes-profile"


class CallJournal:
    """Журнал вызовов инструментов (JSON Lines)."""

    def __init__(self, path: Path) -> None:
        """Задать путь к журналу."""
        self._path = path

    def write(self, record: Mapping[str, Any]) -> None:
        """Дописать запись."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": time.time(), **record}, ensure_ascii=False) + "\n")


class CallerAuthenticator:
    """Определяет мастера по токену профиля и тикету запуска."""

    def __init__(self, registry: MasterRegistry, tickets: TicketCodec) -> None:
        """Получить реестр и кодек тикетов."""
        self._registry = registry
        self._tickets = tickets

    def authenticate(
        self, headers: Mapping[str, str] | None, ticket: str
    ) -> tuple[MasterRecord, CapabilityTicket]:
        """Проверить токен профиля, заголовок профиля и тикет; всё должно указывать на одного мастера."""
        normalized = {key.lower(): value for key, value in (headers or {}).items()}
        token = normalized.get("authorization", "").removeprefix("Bearer ").strip()
        record = self._registry.by_mcp_token().get(token)
        if record is None:
            raise PermissionError("Неизвестный токен профиля")
        if normalized.get(PROFILE_HEADER) not in {None, record.profile}:
            raise PermissionError("Заголовок профиля не совпадает с токеном")
        parsed = self._tickets.verify(ticket)
        if parsed.master_id != record.master_id:
            raise InvalidTicketError("Тикет выдан для другого мастера")
        return record, parsed


class BeautyToolsStub:
    """Инструменты агента. Каждый метод — MCP-инструмент."""

    def __init__(self, authenticator: CallerAuthenticator, journal: CallJournal) -> None:
        """Получить зависимости."""
        self._auth = authenticator
        self._journal = journal

    def register(self, server: MCPServer) -> None:
        """Зарегистрировать инструменты на сервере."""
        server.add_tool(self.whoami, name="whoami", description="Диагностика: кто я (мастер, роль)")
        server.add_tool(
            self.list_services, name="list_services", description="Услуги мастера: длительность и цена"
        )
        server.add_tool(self.find_free_slots, name="find_free_slots", description="Свободные слоты мастера")
        server.add_tool(
            self.find_clients,
            name="find_clients",
            description="Поиск клиентов мастера по имени или последним цифрам телефона (только для мастера)",
        )
        server.add_tool(
            self.book_appointment, name="book_appointment", description="Записать клиента на слот"
        )
        server.add_tool(
            self.send_message,
            name="send_message",
            description="Отправить сообщение в текущий диалог. Единственный способ ответить клиенту.",
        )

    async def whoami(self, ticket: str, ctx: Context) -> dict[str, Any]:
        """Вернуть мастера и роль запуска."""
        record, parsed = self._enter("whoami", ticket, ctx, {})
        return {
            "master": record.display_name,
            "face": parsed.face.value,
            "client_card_id": parsed.client_card_id,
        }

    async def list_services(self, ticket: str, ctx: Context) -> list[dict[str, Any]]:
        """Список услуг."""
        self._enter("list_services", ticket, ctx, {})
        return [asdict(service) for service in SERVICES]

    async def find_free_slots(self, ticket: str, ctx: Context, date: str | None = None) -> list[str]:
        """Свободные слоты (фильтр по дате ``YYYY-MM-DD``)."""
        self._enter("find_free_slots", ticket, ctx, {"date": date})
        return [
            slot for slot in FREE_SLOTS if slot not in BUSY_SLOTS and (date is None or slot.startswith(date))
        ]

    async def find_clients(self, ticket: str, ctx: Context, query: str) -> list[dict[str, str]]:
        """Поиск клиентов: мастеру — все совпадения, ресепшну — только свой клиент."""
        _, parsed = self._enter("find_clients", ticket, ctx, {"query": query})
        visible: tuple[FakeClient, ...] = CLIENTS
        if parsed.face is AgentFace.FRONT_DESK:
            visible = tuple(client for client in CLIENTS if client.card_id == parsed.client_card_id)
        needle = query.strip().lower()
        return [
            {"card_id": client.card_id, "name": client.name, "phone_tail": client.phone[-4:]}
            for client in visible
            if needle in client.name.lower() or client.phone.endswith(needle)
        ]

    async def book_appointment(
        self, ticket: str, ctx: Context, slot: str, client_card_id: str | None = None
    ) -> dict[str, Any]:
        """Записать клиента; ресепшн записывает только своего клиента."""
        _, parsed = self._enter(
            "book_appointment", ticket, ctx, {"slot": slot, "client_card_id": client_card_id}
        )
        target = parsed.client_card_id if parsed.face is AgentFace.FRONT_DESK else client_card_id
        if target is None:
            return {"ok": False, "error": "Не указан клиент"}
        if slot in BUSY_SLOTS:
            return {
                "ok": False,
                "error": "Слот занят",
                "busy_by": BUSY_SLOTS[slot] if parsed.face is AgentFace.BACK_OFFICE else None,
            }
        return {"ok": True, "slot": slot, "client_card_id": target}

    async def send_message(
        self, ticket: str, ctx: Context, text: str, sources: list[str] | None = None
    ) -> dict[str, Any]:
        """Отправить сообщение в диалог тикета (с пометкой «ответ ИИ»)."""
        _, parsed = self._enter("send_message", ticket, ctx, {"text": text, "sources": sources or []})
        return {"ok": True, "conversation_id": parsed.conversation_id, "author": "agent"}

    def _enter(
        self, tool: str, ticket: str, ctx: Context, arguments: Mapping[str, Any]
    ) -> tuple[MasterRecord, CapabilityTicket]:
        """Аутентифицировать вызов и записать его в журнал (в том числе отказ)."""
        headers = ctx.headers
        try:
            record, parsed = self._auth.authenticate(headers, ticket)
        except PermissionError as error:
            self._journal.write({"tool": tool, "denied": str(error), "arguments": dict(arguments)})
            raise
        self._journal.write(
            {
                "tool": tool,
                "master_id": record.master_id,
                "profile": record.profile,
                "profile_header": {key.lower(): value for key, value in (headers or {}).items()}.get(
                    PROFILE_HEADER
                ),
                "face": parsed.face.value,
                "client_card_id": parsed.client_card_id,
                "conversation_id": parsed.conversation_id,
                "arguments": dict(arguments),
            }
        )
        return record, parsed


class StubServerFactory:
    """Собирает MCP-сервер заглушки."""

    def __init__(self, registry_path: Path, journal_path: Path, ticket_secret: bytes) -> None:
        """Задать пути и ключ тикетов."""
        self._registry = MasterRegistry(registry_path)
        self._journal = CallJournal(journal_path)
        self._tickets = TicketCodec(ticket_secret)

    def create(self) -> MCPServer:
        """MCP-сервер с инструментами."""
        server = MCPServer(name="beauty-tools", instructions="Инструменты администратора мастера (спайк).")
        BeautyToolsStub(CallerAuthenticator(self._registry, self._tickets), self._journal).register(server)
        return server
