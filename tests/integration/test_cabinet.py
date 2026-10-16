"""Кабинет мастера на реальном PostgreSQL: роль, график, решения по заявкам, чаты, поток."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DemoMasterSeeder
from beauty.contexts.tenancy.application.commands import AssignOwner, RegisterMaster
from beauty.entrypoints.api import ApiApplicationFactory
from tests.integration.contract import assert_matches_schema
from tests.integration.helpers import EventPump, login
from tests.integration.test_booking import BASE, Client, free_slot, new_client, parse_sse, service_id

pytestmark = pytest.mark.integration

API = "/api/v1"
OWNER_PHONE = "+77010006001"


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
    """Доставка событий outbox консьюмерам и в realtime-хаб."""
    return EventPump(container)


@pytest.fixture
async def master(http: httpx.AsyncClient, container: ApplicationContainer) -> dict[str, str]:
    """Демо-мастер с владельцем; заголовки его кабинета."""
    await DemoMasterSeeder(container.mediator).seed(OWNER_PHONE)
    token = await login(http, container.mediator, 6001, OWNER_PHONE.removeprefix("+"))
    return {"Authorization": f"Bearer {token}"}


async def booked(
    http: httpx.AsyncClient, container: ApplicationContainer, pump: EventPump, user: int
) -> Client:
    """Клиент, оставивший заявку через чат."""
    client = await new_client(http, container, user)
    service = await service_id(http)
    slot = await free_slot(http, service)
    await client.send({"kind": "book_slot", "service_id": service, "start": slot["start"]})
    await pump.drain()
    return client


async def inbox(http: httpx.AsyncClient, headers: dict[str, str], **params: str) -> dict[str, Any]:
    """Список чатов (проверенный по контракту)."""
    response = await http.get(f"{API}/me/conversations", params=params, headers=headers)
    assert response.status_code == 200, response.text
    assert_matches_schema(response.json(), "ConversationList")
    body: dict[str, Any] = response.json()
    return body


async def test_master_role(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Кабинет открыт только владельцу страницы."""
    me = await http.get(f"{API}/me", headers=master)
    assert me.status_code == 200, me.text
    assert_matches_schema(me.json(), "MasterPage")
    assert me.json()["slug"] == "alisa"

    client = await new_client(http, container, 6002)
    denied = await http.get(f"{API}/me", headers=client.headers)
    assert (denied.status_code, denied.json()["code"]) == (403, "not_a_master")
    assert (await http.get(f"{API}/me/conversations")).status_code == 401


async def test_schedule_and_decisions(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Заявка видна в графике со ссылкой на чат; подтверждение из кабинета доходит до клиента."""
    client = await booked(http, container, pump, 6011)
    card = (await client.history())[-1]["appointment"]
    day = card["start"][:10]

    schedule = await http.get(f"{API}/me/schedule", params={"date": day}, headers=master)
    assert schedule.status_code == 200, schedule.text
    body = schedule.json()
    assert_matches_schema(body, "DaySchedule")
    assert len(body["week"]) == 7
    assert body["week"][6]["day_off"] is True  # воскресенье — выходной
    kinds = [item["kind"] for item in body["items"]]
    assert {"appointment", "free", "break"} <= set(kinds)
    item = next(i for i in body["items"] if i["kind"] == "appointment")
    assert item["appointment"]["id"] == card["id"]
    assert item["conversation_id"] == client.conversation_id
    assert body["summary"]["pending_requests"] == 1
    starts = [i.get("start") or i["appointment"]["start"] for i in body["items"]]
    assert starts == sorted(starts)
    worked = sum(1 for i in body["items"] if i["kind"] in ("free", "appointment"))
    assert worked >= 2

    other = await container.mediator.send(RegisterMaster("dana", "Дана", "Дана", "Даны", "Дане"))
    assert other
    await container.mediator.send(AssignOwner("dana", "+77010006099"))
    stranger = {"Authorization": f"Bearer {await login(http, container.mediator, 6099, '77010006099')}"}
    foreign = await http.post(f"{API}/me/appointments/{card['id']}/confirm", headers=stranger)
    assert (foreign.status_code, foreign.json()["code"]) == (404, "appointment_not_found")

    confirmed = await http.post(f"{API}/me/appointments/{card['id']}/confirm", headers=master)
    assert confirmed.status_code == 200, confirmed.text
    assert_matches_schema(confirmed.json(), "Appointment")
    again = await http.post(f"{API}/me/appointments/{card['id']}/decline", headers=master)
    assert (again.status_code, again.json()["code"]) == (409, "appointment_not_pending")
    await pump.drain()
    assert (await client.history())[-1]["text"].startswith("Запись подтверждена")
    chats = await inbox(http, master)
    assert chats["items"][0]["needs_me"] is None


async def test_decline_with_alternatives(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """«Предложить другое»: клиенту приходит предупреждение и новые окна той же услуги."""
    client = await booked(http, container, pump, 6021)
    card = (await client.history())[-1]["appointment"]
    assert (await inbox(http, master))["items"][0]["needs_me"] == "request"
    declined = await http.post(
        f"{API}/me/appointments/{card['id']}/decline", json={"offer_alternatives": True}, headers=master
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["cancelled_by"] == "master"
    await pump.drain()
    history = await client.history()
    assert history[-2]["tone"] == "warning"
    offer = history[-1]
    assert offer["kind"] == "slot_offer"
    assert all(s["service_id"] == card["service"]["id"] for s in offer["slots"])


async def test_inbox_reply_and_handler(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Вопрос клиента → «нужны вы»; поиск; чтение; ответ мастера забирает диалог."""
    quiet = await new_client(http, container, 6031)
    asking = await new_client(http, container, 6032)
    await asking.send({"kind": "text", "text": "Есть ли парковка рядом?"})
    await pump.drain()

    chats = await inbox(http, master)
    assert chats["counts"] == {"all": 2, "needs_me": 1, "agent": 2, "me": 0}
    top = chats["items"][0]
    assert top["id"] == asking.conversation_id
    assert (top["needs_me"], top["unread"], top["handler"]) == ("question", 1, "agent")
    assert top["last_message"]["preview"] == "Есть ли парковка рядом?"
    assert top["client"]["display_name"] == "Новый клиент · …60 32"
    assert top["client"]["phone_masked"] == "+7 701 ••• 60 32"

    assert [c["id"] for c in (await inbox(http, master, filter="needs_me"))["items"]] == [
        asking.conversation_id
    ]
    assert [c["id"] for c in (await inbox(http, master, q="парковк"))["items"]] == [asking.conversation_id]
    assert [c["id"] for c in (await inbox(http, master, q="6031"))["items"]] == [quiet.conversation_id]
    assert (await inbox(http, master, q="50%_"))["items"] == []

    path = f"{API}/me/conversations/{asking.conversation_id}"
    history = await http.get(f"{path}/messages", headers=master)
    assert_matches_schema(history.json(), "MessagePage")
    summary = await http.get(path, headers=master)
    assert_matches_schema(summary.json(), "ConversationSummary")
    assert summary.json()["unread"] == 0

    reply = {"client_id": str(uuid4()), "kind": "text", "text": "Да, во дворе."}
    sent = await http.post(f"{path}/messages", json=reply, headers=master)
    assert sent.status_code == 201, sent.text
    assert_matches_schema(sent.json(), "MasterSendResult")
    assert sent.json()["handler"] == "master"
    assert (await http.post(f"{path}/messages", json=reply, headers=master)).json()["message"]["id"] == (
        sent.json()["message"]["id"]
    )
    assert (await asking.history())[-1]["author"] == "master"
    after = (await http.get(path, headers=master)).json()
    assert (after["handler"], after["needs_me"]) == ("master", None)

    back = await http.put(f"{path}/handler", json={"handler": "agent"}, headers=master)
    assert back.json() == {"handler": "agent"}
    foreign = await http.get(f"{API}/me/conversations/{uuid4()}", headers=master)
    assert foreign.status_code == 404


async def test_master_events_stream(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Поток кабинета: новая заявка (сообщения, сводка, запись); переподключение — reset."""
    stream = asyncio.create_task(http.get(f"{API}/me/events", headers=master))
    await asyncio.sleep(0.1)
    client = await booked(http, container, pump, 6041)
    response = await asyncio.wait_for(stream, timeout=5)
    frames = parse_sse(response.text)
    events = {f["event"] for f in frames}
    assert {"message.created", "conversation.updated", "appointment.updated"} <= events
    for frame in frames:
        assert_matches_schema(frame["data"], "MasterEvent")
    created = [f["data"] for f in frames if f["event"] == "message.created"]
    assert {f["conversation_id"] for f in created} == {client.conversation_id}
    assert [f["id"] for f in frames] == [str(n) for n in range(1, len(frames) + 1)]

    resumed = await http.get(f"{API}/me/events", headers={**master, "Last-Event-ID": "7"})
    assert parse_sse(resumed.text)[0]["data"] == {"type": "reset"}
