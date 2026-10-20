"""Клиенты мастера на реальном PostgreSQL: список, карточка, имя и заметки."""

from __future__ import annotations

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
from tests.integration.test_booking import BASE, new_client
from tests.integration.test_cabinet import API, booked, inbox

pytestmark = pytest.mark.integration

OWNER_PHONE = "+77010007001"


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
    token = await login(http, container.mediator, 7001, OWNER_PHONE.removeprefix("+"))
    return {"Authorization": f"Bearer {token}"}


async def clients(http: httpx.AsyncClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    """Страница клиентов (по контракту)."""
    response = await http.get(f"{API}/me/clients", params=params, headers=headers)
    assert response.status_code == 200, response.text
    assert_matches_schema(response.json(), "MasterClientPage")
    body: dict[str, Any] = response.json()
    return body


async def card(response: httpx.Response | None = None, status: int = 200, **get: Any) -> dict[str, Any]:
    """Карточка из ответа (по контракту)."""
    if response is None:
        response = await get["http"].get(f"{API}/me/clients/{get['client']}", headers=get["headers"])
    assert response.status_code == status, response.text
    assert_matches_schema(response.json(), "MasterClientCard")
    body: dict[str, Any] = response.json()
    return body


async def test_list_card_rename_and_notes(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Список с поиском и фильтром; имя доходит до чата и графика; заметки без дублей."""
    with_request = await booked(http, container, pump, 7011)
    quiet = await new_client(http, container, 7012)
    await quiet.send({"kind": "text", "text": "Здравствуйте"})
    await pump.drain()

    page = await clients(http, master)
    assert page["total"] == 2
    by_phone = {c["phone_masked"][-5:]: c for c in page["items"]}
    booked_row, quiet_row = by_phone["70 11"], by_phone["70 12"]
    assert booked_row["next_visit_at"] is not None
    assert quiet_row["next_visit_at"] is None
    assert (booked_row["named"], booked_row["visits"], booked_row["notes"]) == (False, 0, 0)
    assert booked_row["display_name"] == "Новый клиент · …70 11"
    assert [c["id"] for c in (await clients(http, master, filter="upcoming"))["items"]] == [booked_row["id"]]
    assert [c["id"] for c in (await clients(http, master, q="7012"))["items"]] == [quiet_row["id"]]
    assert (await clients(http, master, q="Никого"))["total"] == 0

    client_id = booked_row["id"]
    detail = await card(http=http, client=client_id, headers=master)
    assert (len(detail["upcoming"]), detail["history"], detail["note_items"]) == (1, [], [])
    assert detail["upcoming"][0]["status"] == "requested"
    assert detail["conversation_id"] == with_request.conversation_id

    renamed = await card(
        await http.put(f"{API}/me/clients/{client_id}/name", json={"name": "  Айгерим "}, headers=master)
    )
    assert (renamed["display_name"], renamed["named"]) == ("Айгерим", True)
    await pump.drain()  # подписка Conversations и Booking на ClientRenamed
    chats = await inbox(http, master)
    assert "Айгерим" in [c["client"]["display_name"] for c in chats["items"]]
    day = detail["upcoming"][0]["start"][:10]
    schedule = (await http.get(f"{API}/me/schedule", params={"date": day}, headers=master)).json()
    names = [
        i["appointment"]["client"]["display_name"] for i in schedule["items"] if i["kind"] == "appointment"
    ]
    assert names == ["Айгерим"]
    assert [c["id"] for c in (await clients(http, master, q="айгер"))["items"]] == [client_id]

    noted = await card(
        await http.post(
            f"{API}/me/clients/{client_id}/notes", json={"text": "Аллергия на лаванду"}, headers=master
        ),
        201,
    )
    again = await card(
        await http.post(
            f"{API}/me/clients/{client_id}/notes", json={"text": "аллергия на лаванду"}, headers=master
        ),
        201,
    )
    assert [n["text"] for n in again["note_items"]] == ["Аллергия на лаванду"]
    note = noted["note_items"][0]
    assert note["author"] == "master"
    removed = await card(
        await http.delete(f"{API}/me/clients/{client_id}/notes/{note['id']}", headers=master)
    )
    assert removed["note_items"] == []
    missing = await http.delete(f"{API}/me/clients/{client_id}/notes/{note['id']}", headers=master)
    assert (missing.status_code, missing.json()["code"]) == (404, "client_note_not_found")

    cleared = await card(
        await http.put(f"{API}/me/clients/{client_id}/name", json={"name": None}, headers=master)
    )
    assert (cleared["display_name"], cleared["named"]) == ("Новый клиент · …70 11", False)
    await pump.drain()
    assert "Айгерим" not in [c["client"]["display_name"] for c in (await inbox(http, master))["items"]]


async def test_client_errors_and_foreign_master(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str], pump: EventPump
) -> None:
    """Чужой или несуществующий клиент — 404; длинное имя и пустая заметка — 422."""
    mine = await new_client(http, container, 7021)
    await mine.send({"kind": "text", "text": "Привет"})
    await pump.drain()
    client_id = (await clients(http, master))["items"][0]["id"]

    unknown = str(uuid4())
    for response in (
        await http.get(f"{API}/me/clients/{unknown}", headers=master),
        await http.put(f"{API}/me/clients/{unknown}/name", json={"name": "X"}, headers=master),
        await http.post(f"{API}/me/clients/{unknown}/notes", json={"text": "X"}, headers=master),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "client_not_found")
    long_name = await http.put(f"{API}/me/clients/{client_id}/name", json={"name": "я" * 61}, headers=master)
    empty_note = await http.post(f"{API}/me/clients/{client_id}/notes", json={"text": ""}, headers=master)
    assert (long_name.status_code, empty_note.status_code) == (422, 422)

    await container.mediator.send(RegisterMaster("dana", "Дана", "Дана", "Даны", "Дане"))
    await container.mediator.send(AssignOwner("dana", "+77010007099"))
    stranger = {"Authorization": f"Bearer {await login(http, container.mediator, 7099, '77010007099')}"}
    assert (await clients(http, stranger))["total"] == 0
    foreign = await http.get(f"{API}/me/clients/{client_id}", headers=stranger)
    assert (foreign.status_code, foreign.json()["code"]) == (404, "client_not_found")
    no_master = await http.get(f"{API}/me/clients", headers=mine.headers)
    assert no_master.status_code == 403
