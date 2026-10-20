"""ИИ-администратор на реальном PostgreSQL: MCP по HTTP, ход ресепшна, передача мастеру.

Hermes здесь заменён сценарным runtime, который ведёт себя как Hermes: получает
инструкции хода, ходит в наш MCP-сервер настоящим MCP-клиентом по HTTP (с токеном
профиля и тикетом хода) и возвращает итоговый текст.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import httpx2
import pytest
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer

from beauty.bootstrap.adapters import AgentClientBook, AgentConversations, AgentMasters
from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DemoMasterSeeder
from beauty.contexts.agent.application.commands import (
    AnswerClient,
    AnswerClientHandler,
    ProvisionAgent,
    ProvisionAgentHandler,
)
from beauty.contexts.agent.application.ports import (
    AgentRuntime,
    ProfileProvisioner,
    ProvisionedProfile,
    RunOutcome,
    RunRequest,
)
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.ticket import AgentFace, RunTicket
from beauty.contexts.agent.infrastructure.uow import SqlAlchemyAgentUnitOfWork
from beauty.entrypoints.api import ApiApplicationFactory
from tests.integration.contract import assert_matches_schema
from tests.integration.helpers import EventPump, login
from tests.integration.test_booking import BASE, Client, new_client

pytestmark = pytest.mark.integration

API = "/api/v1"
TOKEN = "mcp-token-alisa-" + "x" * 24
OWNER_PHONE = "+77010007001"

type ToolCall = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@pytest.fixture(scope="session")
def app(container: ApplicationContainer) -> FastAPI:
    """Приложение без realtime-моста."""
    return ApiApplicationFactory(container, enable_realtime_bridge=False).create()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP-клиент поверх ASGI."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        yield client


type McpServerFactory = Callable[[], MCPServer]


@pytest.fixture
def mcp_app(container: ApplicationContainer) -> McpServerFactory:
    """Фабрика MCP-серверов ``beauty-tools``: менеджер сессий запускается один раз на экземпляр
    и в той же задаче, что и клиент, — поэтому сервер на каждую MCP-сессию."""
    return container.agent.mcp_server


@pytest.fixture
async def alisa(container: ApplicationContainer) -> AgentProfile:
    """Демо-мастер с ИИ-администратором (профиль без Hermes — секреты известны тесту)."""
    master_id = await DemoMasterSeeder(container.mediator).seed(OWNER_PHONE)
    profile = AgentProfile.register(
        master_id=master_id,
        profile_name="m-alisa",
        runs_api_key="runs",
        mcp_token=TOKEN,
        now=container.clock.now(),
    )
    async with SqlAlchemyAgentUnitOfWork(container.session_factory, container.outbox_writer) as uow:
        uow.profiles.add(profile)
        await uow.commit()
    return profile


@asynccontextmanager
async def mcp_session(
    servers: McpServerFactory, token: str, profile: str | None = None
) -> AsyncIterator[ToolCall]:
    """MCP-клиент, как его настраивает Hermes: Bearer-токен профиля и заголовок профиля."""
    headers = {"Authorization": f"Bearer {token}"}
    if profile is not None:
        headers["X-Hermes-Profile"] = profile
    server = servers()
    transport = httpx2.ASGITransport(app=server.streamable_http_app(host="0.0.0.0"))
    async with (
        server.session_manager.run(),
        httpx2.AsyncClient(transport=transport, base_url="http://mcp:8765", headers=headers) as client,
        streamable_http_client("http://mcp:8765/mcp", http_client=client) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()

        async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            result = await session.call_tool(name, arguments)
            text = "".join(getattr(part, "text", "") for part in result.content)
            if result.is_error:
                return {"tool_error": text}
            body: dict[str, Any] = json.loads(text)
            return body

        yield call


class McpScriptRuntime(AgentRuntime):
    """Runtime-сценарий: ходит в MCP по HTTP, как Hermes."""

    def __init__(
        self, servers: McpServerFactory, script: Callable[[ToolCall, str, str], Awaitable[str]]
    ) -> None:
        """``script(call, ticket, input)`` → итоговый текст хода."""
        self._servers = servers
        self._script = script
        self.requests: list[RunRequest] = []

    @property
    def enabled(self) -> bool:
        """Включён."""
        return True

    async def run(self, request: RunRequest) -> RunOutcome:
        """Достать тикет из инструкций и выполнить сценарий."""
        self.requests.append(request)
        match = re.search(r"Тикет хода: (t-[a-z0-9]+)", request.instructions)
        assert match, request.instructions
        async with mcp_session(self._servers, TOKEN, request.profile_name) as call:
            return RunOutcome("completed", await self._script(call, match.group(1), request.input))


async def answer(container: ApplicationContainer, runtime: AgentRuntime, client: Client, text: str) -> None:
    """Клиент пишет, событие доставлено, агент делает ход."""
    sent = await client.send({"kind": "text", "text": text})
    await EventPump(container).drain()
    handler = AnswerClientHandler(
        lambda: SqlAlchemyAgentUnitOfWork(container.session_factory, container.outbox_writer),
        runtime,
        AgentMasters(lambda: container.mediator),
        AgentConversations(lambda: container.mediator),
        AgentClientBook(lambda: container.mediator),
        container.clock,
        timedelta(minutes=10),
    )
    await handler.handle(AnswerClient(UUID(client.conversation_id), UUID(sent.json()["id"]), text))
    await EventPump(container).drain()


async def test_agent_books_through_mcp_and_replies(
    http: httpx.AsyncClient, container: ApplicationContainer, mcp_app: McpServerFactory, alisa: AgentProfile
) -> None:
    """Ход: поиск окон и заявка через MCP → ответ ИИ в чате → карточка заявки и «нужны вы»."""
    client = await new_client(http, container, 7011)
    service = str((await http.get(f"{API}/masters/alisa")).json()["services"][1]["id"])

    async def script(call: ToolCall, ticket: str, text: str) -> str:
        assert text == "Хочу на массаж в ближайшее время"
        slots = await call("find_free_slots", {"ticket": ticket, "service_id": service})
        assert slots.get("ok"), slots
        booked = await call(
            "book_appointment", {"ticket": ticket, "service_id": service, "start": slots["slots"][0]["start"]}
        )
        assert booked["ok"], booked
        mine = await call("my_appointments", {"ticket": ticket})
        assert [a["status"] for a in mine["appointments"]] == ["requested"]
        return "Записала вас, Алиса подтвердит заявку."

    runtime = McpScriptRuntime(mcp_app, script)
    await answer(container, runtime, client, "Хочу на массаж в ближайшее время")

    (request,) = runtime.requests
    assert request.session_id == client.conversation_id
    assert "service_id:" in request.instructions
    history = await client.history()
    assert [(m["author"], m["kind"]) for m in history] == [
        ("client", "text"),
        ("agent", "text"),
        ("agent", "booking_card"),
    ]
    assert history[1]["ai_generated"] is True
    assert history[2]["appointment"]["status"] == "requested"
    master = {"Authorization": f"Bearer {await login(http, container.mediator, 7001, OWNER_PHONE[1:])}"}
    chats = (await http.get(f"{API}/me/conversations", headers=master)).json()
    assert chats["items"][0]["needs_me"] == "request"


async def test_handoff_note_is_for_master_only(
    http: httpx.AsyncClient, container: ApplicationContainer, mcp_app: McpServerFactory, alisa: AgentProfile
) -> None:
    """Передача мастеру: заметка видна в кабинете, клиенту — нет; «нужны вы» остаётся."""
    client = await new_client(http, container, 7021)

    async def script(call: ToolCall, ticket: str, _text: str) -> str:
        done = await call("handoff_to_master", {"ticket": ticket, "summary": "спрашивает про парковку"})
        assert done["ok"], done
        return "Уточню у Алисы и отвечу здесь."

    await answer(container, McpScriptRuntime(mcp_app, script), client, "Есть парковка?")
    assert [(m["author"], m["kind"]) for m in await client.history()] == [
        ("client", "text"),
        ("agent", "text"),
    ]
    events = await client.events("0")
    assert "agent_note" not in {f["data"]["message"]["kind"] for f in events if "message" in f["data"]}

    master = {"Authorization": f"Bearer {await login(http, container.mediator, 7002, OWNER_PHONE[1:])}"}
    path = f"{API}/me/conversations/{client.conversation_id}"
    page = (await http.get(f"{path}/messages", headers=master)).json()
    assert_matches_schema(page, "MessagePage")
    notes = [m for m in page["items"] if m["kind"] == "agent_note"]
    assert [n["text"] for n in notes] == ["Агент передал вам: спрашивает про парковку"]
    assert (await http.get(path, headers=master)).json()["needs_me"] == "question"


async def test_agent_remembers_client_fact_for_master(
    http: httpx.AsyncClient, container: ApplicationContainer, mcp_app: McpServerFactory, alisa: AgentProfile
) -> None:
    """Агент сохраняет факт о клиенте через MCP; мастер видит заметку «ИИ», следующий ход — тоже."""
    client = await new_client(http, container, 7031)

    async def remember(call: ToolCall, ticket: str, _text: str) -> str:
        done = await call("remember_client", {"ticket": ticket, "note": "Аллергия на лаванду"})
        assert done["ok"], done
        return "Учту, спасибо!"

    await answer(container, McpScriptRuntime(mcp_app, remember), client, "У меня аллергия на лаванду")
    master = {"Authorization": f"Bearer {await login(http, container.mediator, 7002, OWNER_PHONE[1:])}"}
    page = (await http.get(f"{API}/me/clients", headers=master)).json()
    client_id = page["items"][0]["id"]
    card = (await http.get(f"{API}/me/clients/{client_id}", headers=master)).json()
    assert_matches_schema(card, "MasterClientCard")
    assert [(n["text"], n["author"]) for n in card["note_items"]] == [("Аллергия на лаванду", "agent")]

    async def reply(_call: ToolCall, _ticket: str, _text: str) -> str:
        return "Хорошо"

    runtime = McpScriptRuntime(mcp_app, reply)
    await answer(container, runtime, client, "Какие масла используете?")
    assert "- Аллергия на лаванду" in runtime.requests[0].instructions


async def test_mcp_rejects_foreign_or_bad_credentials(
    http: httpx.AsyncClient, container: ApplicationContainer, mcp_app: McpServerFactory, alisa: AgentProfile
) -> None:
    """Токен, заголовок профиля и тикет проверяются на каждом вызове."""
    client = await new_client(http, container, 7031)
    tickets: list[str] = []

    async def script(_call: ToolCall, ticket: str, _text: str) -> str:
        tickets.append(ticket)
        return "Здравствуйте!"

    await answer(container, McpScriptRuntime(mcp_app, script), client, "Привет")
    (ticket,) = tickets
    service = str((await http.get(f"{API}/masters/alisa")).json()["services"][0]["id"])
    arguments = {"ticket": ticket, "service_id": service}

    async with mcp_session(mcp_app, "foreign-token-" + "y" * 24) as call:
        assert "tool_error" in await call("find_free_slots", arguments)
    async with mcp_session(mcp_app, TOKEN, "m-someone-else") as call:
        assert "tool_error" in await call("find_free_slots", arguments)
    async with mcp_session(mcp_app, TOKEN, "m-alisa") as call:
        assert "tool_error" in await call("find_free_slots", {**arguments, "ticket": "t-zzzzzzzz"})
        assert (await call("find_free_slots", arguments))["ok"] is True
        refused = await call("cancel_appointment", {"ticket": ticket, "appointment_id": str(uuid4())})
        assert refused["ok"] is False


class RecordingProvisioner(ProfileProvisioner):
    """Профили «создаются» без Hermes; имена запоминаются."""

    def __init__(self) -> None:
        self.created: list[str] = []

    async def create(self, profile_name: str, master_name: str, face: AgentFace) -> ProvisionedProfile:
        self.created.append(profile_name)
        return ProvisionedProfile(f"runs-{profile_name}", f"token-{profile_name}-" + "x" * 24)


async def test_provision_adds_office_to_existing_profile(
    container: ApplicationContainer, alisa: AgentProfile
) -> None:
    """Профиль ресепшна из итерации 4: повторный provision добавляет только кабинет, третий — ничего."""
    provisioner = RecordingProvisioner()
    handler = ProvisionAgentHandler(
        lambda: SqlAlchemyAgentUnitOfWork(container.session_factory, container.outbox_writer),
        provisioner,
        AgentMasters(lambda: container.mediator),
        container.clock,
    )
    assert await handler.handle(ProvisionAgent(alisa.master_id)) == "m-alisa"
    assert await handler.handle(ProvisionAgent(alisa.master_id)) == "m-alisa"
    assert provisioner.created == ["m-alisa-office"]


async def test_latest_ticket_of_thread(container: ApplicationContainer, alisa: AgentProfile) -> None:
    """Последний тикет переписки (ресепшн) и кабинета (переписки нет) — по времени выдачи."""
    now = container.clock.now()
    conversation = uuid4()

    def front(at: timedelta) -> RunTicket:
        return RunTicket.issue(
            master_id=alisa.master_id,
            conversation_id=conversation,
            client_id=uuid4(),
            now=now + at,
            ttl=timedelta(minutes=10),
        )

    stale, current = front(timedelta()), front(timedelta(minutes=1))
    office = RunTicket.issue_office(master_id=alisa.master_id, now=now, ttl=timedelta(minutes=10))
    async with SqlAlchemyAgentUnitOfWork(container.session_factory, container.outbox_writer) as uow:
        for ticket in (current, stale, office):
            uow.tickets.add(ticket)
        await uow.commit()
    async with SqlAlchemyAgentUnitOfWork(container.session_factory, container.outbox_writer) as uow:
        latest = await uow.tickets.latest(alisa.master_id, AgentFace.FRONT_DESK, conversation)
        latest_office = await uow.tickets.latest(alisa.master_id, AgentFace.BACK_OFFICE, None)
        assert latest is not None
        assert latest.id == current.id
        assert latest_office is not None
        assert latest_office.id == office.id
        assert await uow.tickets.latest(alisa.master_id, AgentFace.FRONT_DESK, uuid4()) is None
