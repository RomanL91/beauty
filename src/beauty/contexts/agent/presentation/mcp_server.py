"""MCP-сервер ``beauty-tools`` — инструменты ИИ-администратора для Hermes.

Аутентификация профиля — ``Authorization: Bearer <MCP-токен>`` из ``.env`` профиля
(+ ``X-Hermes-Profile``, который Hermes подставляет сам), авторизация действия — тикет
хода. Отказ в доступе — ошибка инструмента; ошибка предметной области (окно заняли) —
обычный результат ``{"ok": false, "error": ...}``, чтобы модель могла её объяснить.
"""

# Без ``from __future__ import annotations``: схемы инструментов строятся по аннотациям.
import logging
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from beauty.contexts.agent.application.errors import UnknownProfileTokenError
from beauty.contexts.agent.application.toolkit import FrontDeskToolkit, ToolCaller
from beauty.contexts.agent.domain.errors import InvalidTicket

logger = logging.getLogger(__name__)

PROFILE_HEADER = "x-hermes-profile"
INSTRUCTIONS = (
    "Инструменты администратора мастера beauty. В каждый вызов передавай ticket — тикет хода "
    "из инструкций, без изменений. Клиент и мастер определяются тикетом."
)


class BeautyToolsServer:
    """Регистрирует инструменты ресепшна на MCP-сервере."""

    def __init__(self, toolkit: FrontDeskToolkit) -> None:
        """Получить инструменты."""
        self._toolkit = toolkit

    def create(self) -> MCPServer:
        """MCP-сервер с инструментами."""
        server = MCPServer(name="beauty-tools", instructions=INSTRUCTIONS)
        toolkit = self._toolkit

        async def find_free_slots(
            ticket: str, service_id: str, ctx: Context, date: str | None = None
        ) -> dict[str, Any]:
            """Свободные окна услуги мастера: ближайшие или начиная с даты date (YYYY-MM-DD)."""
            caller = await self._caller(ctx, ticket, "find_free_slots")
            return await toolkit.find_free_slots(caller, service_id, date)

        async def book_appointment(ticket: str, service_id: str, start: str, ctx: Context) -> dict[str, Any]:
            """Записать клиента: start — время окна из find_free_slots. Это заявка, мастер подтвердит."""
            caller = await self._caller(ctx, ticket, "book_appointment")
            return await toolkit.book_appointment(caller, service_id, start)

        async def my_appointments(ticket: str, ctx: Context) -> dict[str, Any]:
            """Будущие заявки и записи клиента к мастеру."""
            caller = await self._caller(ctx, ticket, "my_appointments")
            return await toolkit.my_appointments(caller)

        async def cancel_appointment(ticket: str, appointment_id: str, ctx: Context) -> dict[str, Any]:
            """Отменить запись клиента (только по его просьбе; appointment_id — из my_appointments)."""
            caller = await self._caller(ctx, ticket, "cancel_appointment")
            return await toolkit.cancel_appointment(caller, appointment_id)

        async def handoff_to_master(ticket: str, summary: str, ctx: Context) -> dict[str, Any]:
            """Передать диалог мастеру: summary — краткий пересказ вопроса клиента для мастера."""
            caller = await self._caller(ctx, ticket, "handoff_to_master")
            return await toolkit.handoff_to_master(caller, summary)

        for tool in (
            find_free_slots,
            book_appointment,
            my_appointments,
            cancel_appointment,
            handoff_to_master,
        ):
            server.add_tool(tool, name=tool.__name__, description=(tool.__doc__ or "").strip())
        return server

    async def _caller(self, ctx: Context, ticket: str, tool: str) -> ToolCaller:
        """Аутентифицировать вызов; отказ — ошибка инструмента и запись в журнал."""
        headers = {key.lower(): value for key, value in (ctx.headers or {}).items()}
        token = headers.get("authorization", "").removeprefix("Bearer ").strip()
        try:
            caller = await self._toolkit.authorize(token, headers.get(PROFILE_HEADER), ticket)
        except (UnknownProfileTokenError, InvalidTicket) as error:
            logger.warning("MCP %s: отказ (%s)", tool, error)
            raise ToolError(str(error)) from error
        logger.info("MCP %s: мастер %s, тикет %s", tool, caller.master_id, caller.ticket_id)
        return caller
