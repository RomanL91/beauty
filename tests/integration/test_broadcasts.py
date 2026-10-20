"""Рассылки на реальном PostgreSQL: черновик с фото, доставка порциями, лимит, запрет."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from beauty.bootstrap.adapters import AgentMasters
from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DemoMasterSeeder
from beauty.contexts.conversations.application.commands import (
    DeliverBroadcast,
    DeliverBroadcastHandler,
    SetBroadcastsAllowed,
)
from beauty.contexts.conversations.infrastructure.uow import SqlAlchemyConversationsUnitOfWork
from beauty.contexts.tenancy.application.commands import AssignOwner, RegisterMaster
from beauty.contexts.tenancy.application.queries import FindMasterId
from beauty.entrypoints.api import ApiApplicationFactory
from tests.integration.contract import assert_matches_schema
from tests.integration.helpers import EventPump, login
from tests.integration.test_booking import BASE, new_client
from tests.integration.test_master_settings import PNG

pytestmark = pytest.mark.integration

API = "/api/v1"
OWNER_PHONE = "+77010008001"


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
    """Доставка событий outbox консьюмерам."""
    return EventPump(container)


@pytest.fixture
async def master(http: httpx.AsyncClient, container: ApplicationContainer) -> dict[str, str]:
    """Демо-мастер с владельцем; заголовки его кабинета."""
    await DemoMasterSeeder(container.mediator).seed(OWNER_PHONE)
    token = await login(http, container.mediator, 8001, OWNER_PHONE.removeprefix("+"))
    return {"Authorization": f"Bearer {token}"}


async def broadcast(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    """Рассылка из ответа (по контракту)."""
    assert response.status_code == status, response.text
    assert_matches_schema(response.json(), "Broadcast")
    body: dict[str, Any] = response.json()
    return body


def problem(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


async def test_broadcast_with_photo_reaches_every_client(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Черновик → фото → отправка → объявление у каждого клиента (порциями, без дублей)."""
    clients = [await new_client(http, container, 8011 + i) for i in range(3)]
    listing = await http.get(f"{API}/me/broadcasts", headers=master)
    assert_matches_schema(listing.json(), "BroadcastList")
    assert listing.json() == {"items": [], "allowed": True, "next_at": None}

    created = await broadcast(
        await http.post(f"{API}/me/broadcasts", json={"text": " С 1 ноября — массаж лица "}, headers=master),
        201,
    )
    assert (created["status"], created["origin"], created["recipients"]) == ("draft", "master", 3)
    path = f"{API}/me/broadcasts/{created['id']}"
    edited = await broadcast(
        await http.put(path, json={"text": "С 1 ноября — массаж лица, −20%"}, headers=master)
    )
    assert edited["text"] == "С 1 ноября — массаж лица, −20%"
    with_photo = await broadcast(
        await http.put(f"{path}/photo", files={"file": ("sale.png", PNG, "image/png")}, headers=master)
    )
    assert with_photo["photo_url"].startswith(f"{API}/media/announcements/")
    served = await http.get(with_photo["photo_url"])
    assert (served.status_code, served.content) == (200, PNG)
    bad = await http.put(f"{path}/photo", files={"file": ("x.txt", b"text", "text/plain")}, headers=master)
    assert problem(bad) == (422, "invalid_photo")

    sending = await broadcast(await http.post(f"{path}/send", headers=master))
    assert (sending["status"], sending["recipients"], sending["started_at"] is not None) == (
        "sending",
        3,
        True,
    )
    # Доставка порциями по одной: повторный проход консьюмера ничего не дублирует.
    deliver = DeliverBroadcastHandler(
        lambda: SqlAlchemyConversationsUnitOfWork(container.session_factory, container.outbox_writer),
        container.clock,
        container.id_generator,
        batch=1,
    )
    assert await deliver.handle(DeliverBroadcast(UUID(created["id"]))) == 3
    await pump.drain()
    sent = await broadcast(await http.get(path, headers=master))
    assert (sent["status"], sent["delivered"]) == ("sent", 3)
    for client in clients:
        announcements = [m for m in await client.history() if m["kind"] == "announcement"]
        assert len(announcements) == 1
        assert announcements[0]["text"] == "С 1 ноября — массаж лица, −20%"
        assert announcements[0]["author"] == "master"
        assert announcements[0]["photo_url"].startswith(f"{API}/media/announcements/")

    chats = (await http.get(f"{API}/me/conversations", headers=master)).json()["items"]
    assert {c["handler"] for c in chats} == {"agent"}  # объявление не забирает диалоги у агента
    assert all(c["last_message"]["preview"].startswith("Объявление: ") for c in chats)

    master_id = await container.mediator.send(FindMasterId("alisa"))
    brief = await AgentMasters(lambda: container.mediator).brief(master_id)
    assert brief is not None
    assert brief.announcements[0].endswith("С 1 ноября — массаж лица, −20% (с фото)")

    assert problem(await http.put(path, json={"text": "Другое"}, headers=master)) == (
        409,
        "broadcast_not_draft",
    )
    assert problem(await http.delete(path, headers=master)) == (409, "broadcast_not_draft")
    second = await broadcast(
        await http.post(f"{API}/me/broadcasts", json={"text": "Ещё"}, headers=master), 201
    )
    cooldown = await http.post(f"{API}/me/broadcasts/{second['id']}/send", headers=master)
    assert problem(cooldown) == (429, "broadcast_cooldown")
    listing = (await http.get(f"{API}/me/broadcasts", headers=master)).json()
    assert listing["next_at"] is not None
    assert [b["status"] for b in listing["items"]] == ["draft", "sent"]
    assert (await http.delete(f"{API}/me/broadcasts/{second['id']}", headers=master)).status_code == 204


async def test_blocked_broadcasts_and_foreign_master(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Запрет из админки — 403; без клиентов — 409; чужая рассылка — 404."""
    created = await broadcast(
        await http.post(f"{API}/me/broadcasts", json={"text": "Отпуск"}, headers=master), 201
    )
    path = f"{API}/me/broadcasts/{created['id']}"
    assert problem(await http.post(f"{path}/send", headers=master)) == (409, "no_recipients")

    await new_client(http, container, 8021)
    master_id = await container.mediator.send(FindMasterId("alisa"))
    await container.mediator.send(SetBroadcastsAllowed(master_id, allowed=False))
    assert (await http.get(f"{API}/me/broadcasts", headers=master)).json()["allowed"] is False
    assert problem(await http.post(f"{path}/send", headers=master)) == (403, "broadcasts_blocked")
    await container.mediator.send(SetBroadcastsAllowed(master_id, allowed=True))
    assert (await broadcast(await http.post(f"{path}/send", headers=master)))["status"] == "sending"

    await container.mediator.send(RegisterMaster("dana", "Дана", "Дана", "Даны", "Дане"))
    await container.mediator.send(AssignOwner("dana", "+77010008099"))
    stranger = {"Authorization": f"Bearer {await login(http, container.mediator, 8099, '77010008099')}"}
    assert problem(await http.get(path, headers=stranger)) == (404, "broadcast_not_found")
    empty = await http.post(f"{API}/me/broadcasts", json={"text": ""}, headers=master)
    assert empty.status_code == 422
