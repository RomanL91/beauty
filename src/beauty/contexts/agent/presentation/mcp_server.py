"""MCP-сервер ``beauty-tools`` — инструменты ИИ-администратора для Hermes.

Два эндпоинта одного процесса: ``/mcp`` — инструменты ресепшна (клиенты), ``/office/mcp`` —
инструменты кабинета (поручения мастера). Профиль Hermes видит только эндпоинт своей роли.

Аутентификация профиля — ``Authorization: Bearer <MCP-токен>`` из ``.env`` профиля
(+ ``X-Hermes-Profile``, который Hermes подставляет сам), авторизация действия — тикет
хода. Отказ в доступе — ошибка инструмента; ошибка предметной области (окно заняли) —
обычный результат ``{"ok": false, "error": ...}``, чтобы модель могла её объяснить.
"""

# Без ``from __future__ import annotations``: схемы инструментов строятся по аннотациям.
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.applications import Starlette

from beauty.contexts.agent.application.access import Grant
from beauty.contexts.agent.application.errors import UnknownProfileTokenError
from beauty.contexts.agent.application.office_tools import OfficeToolkit
from beauty.contexts.agent.application.toolkit import FrontDeskToolkit, ToolCaller
from beauty.contexts.agent.domain.errors import InvalidTicket

logger = logging.getLogger(__name__)

PROFILE_HEADER = "x-hermes-profile"
OFFICE_PATH = "/office/mcp"
INSTRUCTIONS = (
    "Инструменты администратора мастера beauty. В каждый вызов передавай ticket — тикет хода "
    "из инструкций, без изменений. Клиент и мастер определяются тикетом."
)
OFFICE_INSTRUCTIONS = (
    "Инструменты кабинета мастера beauty: график, записи, клиенты, выходные. В каждый вызов "
    "передавай ticket — тикет хода из инструкций, без изменений. Мастер определяется тикетом."
)


async def _authorized[T](
    authorize: Callable[[str, str | None, str], Awaitable[T]], ctx: Context, ticket: str, tool: str
) -> T:
    """Аутентифицировать вызов; отказ — ошибка инструмента и запись в журнал."""
    headers = {key.lower(): value for key, value in (ctx.headers or {}).items()}
    token = headers.get("authorization", "").removeprefix("Bearer ").strip()
    try:
        caller = await authorize(token, headers.get(PROFILE_HEADER), ticket)
    except (UnknownProfileTokenError, InvalidTicket) as error:
        logger.warning("MCP %s: отказ (%s)", tool, error)
        raise ToolError(str(error)) from error
    logger.info("MCP %s: тикет %s", tool, ticket)
    return caller


def _register(server: MCPServer, tools: tuple[Callable[..., Awaitable[dict[str, Any]]], ...]) -> MCPServer:
    for tool in tools:
        server.add_tool(tool, name=tool.__name__, description=inspect.cleandoc(tool.__doc__ or ""))
    return server


class BeautyToolsServer:
    """Инструменты ресепшна (эндпоинт ``/mcp``)."""

    def __init__(self, toolkit: FrontDeskToolkit) -> None:
        """Получить инструменты."""
        self._toolkit = toolkit

    def create(self) -> MCPServer:
        """MCP-сервер с инструментами ресепшна."""
        toolkit = self._toolkit

        async def caller(ctx: Context, ticket: str, tool: str) -> ToolCaller:
            return await _authorized(toolkit.authorize, ctx, ticket, tool)

        async def find_free_slots(
            ticket: str, service_id: str, ctx: Context, date: str | None = None
        ) -> dict[str, Any]:
            """Свободные окна услуги мастера: ближайшие или начиная с даты date (YYYY-MM-DD)."""
            return await toolkit.find_free_slots(
                await caller(ctx, ticket, "find_free_slots"), service_id, date
            )

        async def book_appointment(ticket: str, service_id: str, start: str, ctx: Context) -> dict[str, Any]:
            """Записать клиента: start — время окна из find_free_slots. Это заявка, мастер подтвердит."""
            granted = await caller(ctx, ticket, "book_appointment")
            return await toolkit.book_appointment(granted, service_id, start)

        async def my_appointments(ticket: str, ctx: Context) -> dict[str, Any]:
            """Будущие заявки и записи клиента к мастеру."""
            return await toolkit.my_appointments(await caller(ctx, ticket, "my_appointments"))

        async def cancel_appointment(ticket: str, appointment_id: str, ctx: Context) -> dict[str, Any]:
            """Отменить запись клиента (только по его просьбе; appointment_id — из my_appointments)."""
            granted = await caller(ctx, ticket, "cancel_appointment")
            return await toolkit.cancel_appointment(granted, appointment_id)

        async def handoff_to_master(ticket: str, summary: str, ctx: Context) -> dict[str, Any]:
            """Передать диалог мастеру: summary — краткий пересказ вопроса клиента для мастера."""
            return await toolkit.handoff_to_master(await caller(ctx, ticket, "handoff_to_master"), summary)

        async def remember_client(ticket: str, note: str, ctx: Context) -> dict[str, Any]:
            """Сохранить в карточку клиента устойчивый факт о нём (аллергия, предпочтения, как обращаться).

            Одна мысль — одна короткая заметка; записи и разовые договорённости не сохраняй.
            """
            return await toolkit.remember_client(await caller(ctx, ticket, "remember_client"), note)

        return _register(
            MCPServer(name="beauty-tools", instructions=INSTRUCTIONS),
            (
                find_free_slots,
                book_appointment,
                my_appointments,
                cancel_appointment,
                handoff_to_master,
                remember_client,
            ),
        )


class OfficeToolsServer:
    """Инструменты кабинета (эндпоинт ``/office/mcp``)."""

    def __init__(self, toolkit: OfficeToolkit) -> None:
        """Получить инструменты."""
        self._toolkit = toolkit

    def create(self) -> MCPServer:
        """MCP-сервер с инструментами кабинета."""
        toolkit = self._toolkit

        async def caller(ctx: Context, ticket: str, tool: str) -> Grant:
            return await _authorized(toolkit.authorize, ctx, ticket, tool)

        async def day_schedule(ticket: str, ctx: Context, date: str | None = None) -> dict[str, Any]:
            """День мастера: записи, заявки (status requested) и свободные окна.

            date — YYYY-MM-DD, по умолчанию сегодня.
            """
            return await toolkit.day_schedule(await caller(ctx, ticket, "day_schedule"), date)

        async def find_free_slots(
            ticket: str, service_id: str, ctx: Context, date: str | None = None
        ) -> dict[str, Any]:
            """Свободные окна услуги: ближайшие или начиная с даты date (YYYY-MM-DD)."""
            granted = await caller(ctx, ticket, "find_free_slots")
            return await toolkit.find_free_slots(granted, service_id, date)

        async def find_clients(ticket: str, query: str, ctx: Context) -> dict[str, Any]:
            """Клиенты мастера по имени или последним цифрам телефона."""
            return await toolkit.find_clients(await caller(ctx, ticket, "find_clients"), query)

        async def book_client(
            ticket: str, client_id: str, service_id: str, start: str, ctx: Context
        ) -> dict[str, Any]:
            """Записать клиента от имени мастера (сразу подтверждено): start — из find_free_slots."""
            granted = await caller(ctx, ticket, "book_client")
            return await toolkit.book_client(granted, client_id, service_id, start)

        async def confirm_request(ticket: str, appointment_id: str, ctx: Context) -> dict[str, Any]:
            """Подтвердить заявку клиента (appointment_id — из day_schedule)."""
            return await toolkit.confirm_request(await caller(ctx, ticket, "confirm_request"), appointment_id)

        async def decline_request(
            ticket: str, appointment_id: str, ctx: Context, offer_alternatives: bool = True
        ) -> dict[str, Any]:
            """Отклонить заявку; offer_alternatives — предложить клиенту другие окна."""
            granted = await caller(ctx, ticket, "decline_request")
            return await toolkit.decline_request(granted, appointment_id, offer_alternatives)

        async def cancel_appointment(
            ticket: str, appointment_id: str, ctx: Context, offer_alternatives: bool = True
        ) -> dict[str, Any]:
            """Отменить запись от имени мастера; клиент получит сообщение (и другие окна)."""
            granted = await caller(ctx, ticket, "cancel_appointment")
            return await toolkit.cancel_appointment(granted, appointment_id, offer_alternatives)

        async def set_day_off(ticket: str, date: str, ctx: Context, off: bool = True) -> dict[str, Any]:
            """Закрыть дату для записи (off=true) или открыть снова (off=false). Записи не отменяет."""
            return await toolkit.set_day_off(await caller(ctx, ticket, "set_day_off"), date, off)

        async def message_client(ticket: str, client_id: str, text: str, ctx: Context) -> dict[str, Any]:
            """Написать клиенту в его чат от имени администратора мастера."""
            granted = await caller(ctx, ticket, "message_client")
            return await toolkit.message_client(granted, client_id, text)

        async def client_card(ticket: str, client_id: str, ctx: Context) -> dict[str, Any]:
            """Карточка клиента: имя, визиты, ближайшие записи и заметки (client_id — из find_clients)."""
            return await toolkit.client_card(await caller(ctx, ticket, "client_card"), client_id)

        async def add_client_note(ticket: str, client_id: str, text: str, ctx: Context) -> dict[str, Any]:
            """Записать в карточку клиента заметку (одна мысль, до 500 символов)."""
            granted = await caller(ctx, ticket, "add_client_note")
            return await toolkit.add_client_note(granted, client_id, text)

        async def rename_client(
            ticket: str, client_id: str, ctx: Context, name: str | None = None
        ) -> dict[str, Any]:
            """Дать клиенту имя (видно в чатах и графике); пустое name — снова подпись по телефону."""
            granted = await caller(ctx, ticket, "rename_client")
            return await toolkit.rename_client(granted, client_id, name)

        async def ask_master(
            ticket: str, question: str, options: list[str], ctx: Context, detail: str | None = None
        ) -> dict[str, Any]:
            """Спросить мастера: вопрос и 2–4 коротких варианта (последний — «Ничего не менять»).

            После вызова закончи ход: ответ мастера придёт следующим сообщением.
            """
            granted = await caller(ctx, ticket, "ask_master")
            return await toolkit.ask_master(granted, question, options, detail)

        return _register(
            MCPServer(name="beauty-office", instructions=OFFICE_INSTRUCTIONS),
            (
                day_schedule,
                find_free_slots,
                find_clients,
                book_client,
                confirm_request,
                decline_request,
                cancel_appointment,
                set_day_off,
                message_client,
                client_card,
                add_client_note,
                rename_client,
                ask_master,
            ),
        )


class McpApplication:
    """ASGI-приложение процесса ``beauty mcp``: оба эндпоинта и их менеджеры сессий."""

    def __init__(self, front_desk: MCPServer, office: MCPServer) -> None:
        """Серверы ресепшна и кабинета."""
        self._front_desk = front_desk
        self._office = office

    def create(self, host: str) -> Starlette:
        """Приложение: ``/mcp`` и ``/office/mcp``."""
        front_desk, office = self._front_desk, self._office
        routes = [
            *front_desk.streamable_http_app(host=host).routes,
            *office.streamable_http_app(streamable_http_path=OFFICE_PATH, host=host).routes,
        ]

        @asynccontextmanager
        async def lifespan(_app: Starlette) -> AsyncIterator[None]:
            async with front_desk.session_manager.run(), office.session_manager.run():
                yield

        return Starlette(routes=routes, lifespan=lifespan)
