"""Поручения мастера ИИ-администратору на реальном PostgreSQL.

API ``/me/assistant``, кадры ленты в ``/me/events``, MCP кабинета по HTTP настоящим
MCP-клиентом (через приложение процесса ``beauty mcp`` с обоими эндпоинтами) и действия
от имени мастера: подтверждение, отмена, выходной, сообщение клиенту. Hermes заменён
сценарным runtime, который ходит в MCP, как Hermes.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import httpx2
import pytest
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from beauty.bootstrap.adapters import AgentMasters
from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DemoMasterSeeder
from beauty.contexts.agent.application.office import NOT_CONNECTED, RunOfficeTurnHandler
from beauty.contexts.agent.application.ports import AgentRuntime, RunOutcome, RunRequest
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.ticket import RunTicket
from beauty.contexts.agent.infrastructure.uow import SqlAlchemyAgentUnitOfWork
from beauty.contexts.agent.presentation.consumers import BackOfficeConsumer
from beauty.contexts.agent.presentation.mcp_server import McpApplication
from beauty.entrypoints.api import ApiApplicationFactory
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from tests.integration.contract import assert_matches_schema
from tests.integration.helpers import EventPump, login
from tests.integration.test_booking import BASE, Client, free_slot, new_client, parse_sse, service_id

pytestmark = pytest.mark.integration

API = "/api/v1"
OWNER_PHONE = "+77010008001"
FRONT_TOKEN = "front-token-alisa-" + "f" * 24
OFFICE_TOKEN = "office-token-alisa-" + "o" * 24

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


@pytest.fixture
def pump(container: ApplicationContainer) -> EventPump:
    """Доставка событий консьюмерам и в realtime-хаб."""
    return EventPump(container)


@pytest.fixture
async def master(http: httpx.AsyncClient, container: ApplicationContainer) -> dict[str, str]:
    """Демо-мастер с ресепшном и кабинетом (профили без Hermes — секреты известны тесту)."""
    master_id = await DemoMasterSeeder(container.mediator).seed(OWNER_PHONE)
    profile = AgentProfile.register(
        master_id=master_id,
        profile_name="m-alisa",
        runs_api_key="runs",
        mcp_token=FRONT_TOKEN,
        now=container.clock.now(),
    )
    profile.attach_office("m-alisa-office", "office-runs", OFFICE_TOKEN, container.clock.now())
    async with SqlAlchemyAgentUnitOfWork(container.session_factory, container.outbox_writer) as uow:
        uow.profiles.add(profile)
        await uow.commit()
    token = await login(http, container.mediator, 8001, OWNER_PHONE[1:])
    return {"Authorization": f"Bearer {token}", "X-Master-Id": str(master_id)}


@asynccontextmanager
async def mcp_session(
    container: ApplicationContainer, path: str, token: str, profile: str | None = None
) -> AsyncIterator[ToolCall]:
    """MCP-клиент, как его настраивает Hermes, к приложению процесса ``beauty mcp``."""
    application = McpApplication(container.agent.mcp_server(), container.agent.office_mcp_server()).create(
        "0.0.0.0"
    )
    headers = {"Authorization": f"Bearer {token}"}
    if profile is not None:
        headers["X-Hermes-Profile"] = profile
    async with (
        application.router.lifespan_context(application),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=application), headers=headers) as client,
        streamable_http_client(f"http://mcp:8765{path}", http_client=client) as streams,
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


class OfficeScript(AgentRuntime):
    """Runtime-сценарий кабинета: по входу хода ходит в ``/office/mcp`` по HTTP, как Hermes."""

    def __init__(
        self, container: ApplicationContainer, script: Callable[[ToolCall, str, str], Awaitable[str]]
    ) -> None:
        """``script(call, ticket, input)`` → итоговый текст хода."""
        self._container = container
        self._script = script
        self.requests: list[RunRequest] = []

    @property
    def enabled(self) -> bool:
        """Включён."""
        return True

    async def run(self, request: RunRequest) -> RunOutcome:
        """Тикет из инструкций — и сценарий."""
        self.requests.append(request)
        match = re.search(r"Тикет хода: (t-[a-z0-9]+)", request.instructions)
        assert match, request.instructions
        async with mcp_session(self._container, "/office/mcp", OFFICE_TOKEN, request.profile_name) as call:
            return RunOutcome("completed", await self._script(call, match.group(1), request.input))


class ScriptedOfficeConsumer(IntegrationEventHandler):
    """Консьюмер кабинета, как в worker, но ход — со сценарным runtime."""

    def __init__(self, container: ApplicationContainer, runtime: AgentRuntime) -> None:
        """Собрать обработчик хода."""
        self._handler = RunOfficeTurnHandler(
            lambda: SqlAlchemyAgentUnitOfWork(container.session_factory, container.outbox_writer),
            runtime,
            AgentMasters(lambda: container.mediator),
            container.clock,
            container.id_generator,
            timedelta(minutes=10),
        )

    async def handle(self, envelope: EventEnvelope) -> None:
        """Ход по событию."""
        await self._handler.handle(BackOfficeConsumer.command(envelope))


def office_pump(container: ApplicationContainer, runtime: AgentRuntime) -> EventPump:
    """Доставка событий, где ходы кабинета делает сценарный runtime."""
    return EventPump(container, {"agent.back_office": ScriptedOfficeConsumer(container, runtime)})


async def give_task(http: httpx.AsyncClient, master: dict[str, str], text: str) -> dict[str, Any]:
    """Мастер даёт поручение текстом."""
    sent = await http.post(
        f"{API}/me/assistant/messages",
        json={"client_id": str(uuid4()), "kind": "text", "text": text},
        headers=master,
    )
    assert sent.status_code == 201, sent.text
    body: dict[str, Any] = sent.json()
    return body


async def feed(http: httpx.AsyncClient, master: dict[str, str]) -> list[dict[str, Any]]:
    """Лента поручений (проверенная по контракту)."""
    response = await http.get(f"{API}/me/assistant/messages", params={"limit": 100}, headers=master)
    assert response.status_code == 200, response.text
    assert_matches_schema(response.json(), "MessagePage")
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def booked(
    http: httpx.AsyncClient, container: ApplicationContainer, pump: EventPump, user: int
) -> Client:
    """Клиент с заявкой через чат."""
    client = await new_client(http, container, user)
    service = await service_id(http)
    slot = await free_slot(http, service)
    await client.send({"kind": "book_slot", "service_id": service, "start": slot["start"]})
    await pump.drain()
    return client


async def test_task_feed_choice_and_stream(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Поручение → лента и кадры /me/events (conversation_id = null); без runtime — служебная строка."""
    assert await feed(http, master) == []
    stream = asyncio.create_task(http.get(f"{API}/me/events", headers=master))
    await asyncio.sleep(0.1)
    body = {"client_id": str(uuid4()), "kind": "text", "text": "Что у меня завтра?"}
    sent = await http.post(f"{API}/me/assistant/messages", json=body, headers=master)
    assert sent.status_code == 201, sent.text
    assert_matches_schema(sent.json(), "Message")
    again = await http.post(f"{API}/me/assistant/messages", json=body, headers=master)
    assert again.json()["id"] == sent.json()["id"]
    await pump.drain()  # ход кабинета: runtime в тестах выключен
    frames = [
        f
        for f in parse_sse((await asyncio.wait_for(stream, timeout=5)).text)
        if f["event"] == "message.created"
    ]
    for frame in frames:
        assert_matches_schema(frame["data"], "MasterEvent")
    assert [(f["data"]["conversation_id"], f["data"]["message"]["author"]) for f in frames] == [
        (None, "master"),
        (None, "agent"),
    ]
    items = await feed(http, master)
    assert [(m["author"], m["kind"], m.get("text")) for m in items] == [
        ("master", "text", "Что у меня завтра?"),
        ("agent", "system", NOT_CONNECTED),
    ]

    client = await new_client(http, container, 8011)
    assert (await http.get(f"{API}/me/assistant/messages", headers=client.headers)).status_code == 403
    bad = await http.post(f"{API}/me/assistant/messages", json={"kind": "text", "text": ""}, headers=master)
    assert bad.status_code == 422


async def test_office_turn_acts_for_the_master(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Ход кабинета по MCP: подтвердить заявку, закрыть дату, написать клиенту — всё доходит."""
    client = await booked(http, container, pump, 8021)
    card = (await client.history())[-1]["appointment"]
    day = card["start"][:10]
    sunday = date.fromisoformat(day) + timedelta(days=(6 - date.fromisoformat(day).weekday()) or 7)

    async def script(call: ToolCall, ticket: str, text: str) -> str:
        assert text == "Подтверди заявку и закрой воскресенье"
        schedule = await call("day_schedule", {"ticket": ticket, "date": day})
        request = next(
            i for i in schedule["items"] if i["kind"] == "appointment" and i["status"] == "requested"
        )
        confirmed = await call(
            "confirm_request", {"ticket": ticket, "appointment_id": request["appointment_id"]}
        )
        assert confirmed["status"] == "confirmed"
        closed = await call("set_day_off", {"ticket": ticket, "date": sunday.isoformat(), "off": True})
        assert closed["day_off"] is True
        (found,) = (await call("find_clients", {"ticket": ticket, "query": "8021"}))["clients"]
        sent = await call(
            "message_client", {"ticket": ticket, "client_id": found["client_id"], "text": "Ждём вас!"}
        )
        assert sent["ok"] is True
        return "Заявку подтвердила, воскресенье закрыла, клиенту написала."

    runtime = OfficeScript(container, script)
    await give_task(http, master, "Подтверди заявку и закрой воскресенье")
    await office_pump(container, runtime).drain()

    (request,) = runtime.requests
    assert request.profile_name == "m-alisa-office"
    assert [(m["author"], m["kind"]) for m in await feed(http, master)] == [
        ("master", "text"),
        ("agent", "text"),
    ]
    assert (await feed(http, master))[-1]["text"].startswith("Заявку подтвердила")
    message, confirmed = (await client.history())[-2:]  # сообщение — в ходе, подтверждение — событием
    assert (message["author"], message["text"], message["ai_generated"]) == ("agent", "Ждём вас!", True)
    assert confirmed["text"].startswith("Запись подтверждена")
    week = (await http.get(f"{API}/me/schedule", params={"date": sunday.isoformat()}, headers=master)).json()
    assert next(d for d in week["week"] if d["date"] == sunday.isoformat())["day_off"] is True


async def test_master_cancels_through_agent_and_choice_starts_next_turn(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Агент спрашивает мастера → выбор → ход «Мастер выбрал …» → отмена; клиенту — окна."""
    client = await booked(http, container, pump, 8031)
    appointment_id = (await client.history())[-1]["appointment"]["id"]

    async def script(call: ToolCall, ticket: str, text: str) -> str:
        if text == "Отмени заявку":
            question = {"question": "Отменить заявку клиента?", "options": ["Да", "Ничего не менять"]}
            assert (await call("ask_master", {"ticket": ticket, **question}))["ok"] is True
            return "Уточняю у мастера."
        assert text == "Мастер выбрал «Да» в ответ на вопрос «Отменить заявку клиента?»."
        done = await call("cancel_appointment", {"ticket": ticket, "appointment_id": appointment_id})
        assert done["status"] == "cancelled"
        return "Отменила, клиенту предложены другие окна."

    office = office_pump(container, OfficeScript(container, script))
    await give_task(http, master, "Отмени заявку")
    await office.drain()
    items = await feed(http, master)
    assert [m["kind"] for m in items] == ["text", "choice"]  # текст хода не дублирует карточку
    card = items[-1]
    assert card["options"][-1]["tone"] == "muted"

    path = f"{API}/me/assistant/choices/{card['choice_id']}"
    chosen = await http.post(path, json={"option_id": "1"}, headers=master)
    assert chosen.status_code == 200, chosen.text
    assert_matches_schema(chosen.json(), "Message")
    assert chosen.json()["selected_option_id"] == "1"
    conflict = await http.post(path, json={"option_id": "2"}, headers=master)
    assert (conflict.status_code, conflict.json()["code"]) == (409, "choice_already_answered")
    missing = await http.post(
        f"{API}/me/assistant/choices/{uuid4()}", json={"option_id": "1"}, headers=master
    )
    assert (missing.status_code, missing.json()["code"]) == (404, "choice_not_found")
    await office.drain()

    assert [m["kind"] for m in await feed(http, master)] == ["text", "choice", "text"]
    assert (await feed(http, master))[-1]["text"].startswith("Отменила")
    history = await client.history()
    assert history[-3]["appointment"]["status"] == "cancelled"
    assert (history[-2]["kind"], history[-2]["tone"]) == ("system", "warning")
    assert history[-1]["kind"] == "slot_offer"


async def test_office_mcp_admits_only_office_credentials(
    container: ApplicationContainer, master: dict[str, str]
) -> None:
    """``/office/mcp`` не пускает токен ресепшна, ``/mcp`` — токен кабинета; тикет — своей роли."""
    async with SqlAlchemyAgentUnitOfWork(container.session_factory, container.outbox_writer) as uow:
        ticket = RunTicket.issue_office(
            master_id=UUID(master["X-Master-Id"]), now=container.clock.now(), ttl=timedelta(minutes=5)
        )
        uow.tickets.add(ticket)
        await uow.commit()
    arguments = {"ticket": ticket.id}
    async with mcp_session(container, "/office/mcp", OFFICE_TOKEN, "m-alisa-office") as call:
        assert (await call("day_schedule", arguments))["ok"] is True
    async with mcp_session(container, "/office/mcp", FRONT_TOKEN, "m-alisa") as call:
        assert "tool_error" in await call("day_schedule", arguments)
    async with mcp_session(container, "/mcp", OFFICE_TOKEN) as call:
        assert "tool_error" in await call("my_appointments", arguments)
    async with mcp_session(container, "/office/mcp", OFFICE_TOKEN, "m-alisa") as call:
        assert "tool_error" in await call("day_schedule", arguments)  # заголовок профиля чужой роли
