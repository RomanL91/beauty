"""Мастер сам ведёт страницу на реальном PostgreSQL: профиль, услуги, часы, выходные, правила,
фото и аватар, публикация. Ответы — по схемам контракта."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DEMO_SLUG, DemoMasterSeeder
from beauty.contexts.tenancy.application.commands import AssignOwner, RegisterMaster
from beauty.entrypoints.api import ApiApplicationFactory
from tests.integration.contract import assert_matches_schema
from tests.integration.helpers import login
from tests.integration.test_booking import BASE, new_client

pytestmark = pytest.mark.integration

API = "/api/v1"
OWNER_PHONE = "+77010010001"
# PNG 1×1 — настоящий файл с сигнатурой формата.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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
async def master(http: httpx.AsyncClient, container: ApplicationContainer) -> dict[str, str]:
    """Демо-мастер (опубликован) и заголовки его кабинета."""
    await DemoMasterSeeder(container.mediator).seed(OWNER_PHONE)
    token = await login(http, container.mediator, 10001, OWNER_PHONE[1:])
    return {"Authorization": f"Bearer {token}"}


async def ok(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    """Ответ с настройками (проверенный по контракту)."""
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    assert_matches_schema(body, "MasterSettings")
    return body


def problem(response: httpx.Response) -> tuple[int, str]:
    """Статус и код problem+json."""
    return response.status_code, response.json()["code"]


async def test_settings_profile_and_rights(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Настройки видит только владелец; профиль меняется и сразу виден на странице."""
    settings = await ok(await http.get(f"{API}/me/settings", headers=master))
    assert (settings["status"], settings["publish_blockers"]) == ("published", [])
    assert settings["working_hours"][0]["weekday"] == 0
    assert set(settings["booking_rules"]) >= {"min_notice_minutes", "horizon_days", "slot_step_minutes"}

    client = await new_client(http, container, 10002)
    assert problem(await http.get(f"{API}/me/settings", headers=client.headers)) == (403, "not_a_master")
    assert (await http.get(f"{API}/me/settings")).status_code == 401

    profile = {
        "display_name": "Алиса Иванова",
        "name_forms": {"nominative": "Алиса", "genitive": "Алисы", "dative": "Алисе"},
        "specialty": "Массаж",
        "address": "Астана, ул. Кенесары, 42",
        "about": "Десять лет практики.",
        "timezone": "Asia/Almaty",
    }
    updated = await ok(await http.put(f"{API}/me/profile", json=profile, headers=master))
    assert updated["page"]["address"] == "Астана, ул. Кенесары, 42"
    public = (await http.get(f"{API}/masters/{DEMO_SLUG}")).json()
    assert (public["display_name"], public["about"]) == ("Алиса Иванова", "Десять лет практики.")
    wrong = await http.put(f"{API}/me/profile", json={**profile, "timezone": "Mars/Base"}, headers=master)
    assert problem(wrong) == (422, "invalid_timezone")


async def test_services_hours_days_off_and_rules(http: httpx.AsyncClient, master: dict[str, str]) -> None:
    """Услуги, рабочие часы с перерывом, выходные даты и правила записи."""
    service = {"title": "Массаж лица", "duration_min": 45, "price": {"amount": 1_000_000, "currency": "KZT"}}
    added = await ok(await http.post(f"{API}/me/services", json=service, headers=master), 201)
    new = next(s for s in added["page"]["services"] if s["title"] == "Массаж лица")
    assert new["description"] == ""
    about = "  Лимфодренаж и лифтинг.\nНе делаю при розацеа.  "
    changed = await ok(
        await http.put(
            f"{API}/me/services/{new['id']}",
            json={**service, "price": None, "description": about},
            headers=master,
        )
    )
    updated = next(s for s in changed["page"]["services"] if s["id"] == new["id"])
    assert (updated["price"], updated["description"]) == (
        None,
        "Лимфодренаж и лифтинг.\nНе делаю при розацеа.",
    )
    too_long = await http.put(
        f"{API}/me/services/{new['id']}", json={**service, "description": "x" * 1001}, headers=master
    )
    assert problem(too_long) == (422, "validation_error")
    archived = await ok(await http.delete(f"{API}/me/services/{new['id']}", headers=master))
    assert all(s["id"] != new["id"] for s in archived["page"]["services"])
    bad_duration = await http.post(f"{API}/me/services", json={**service, "duration_min": 7}, headers=master)
    assert problem(bad_duration) == (422, "invalid_service_duration")

    hours = {
        "days": [
            {
                "weekday": 0,
                "intervals": [{"start": "10:00", "end": "14:00"}, {"start": "15:00", "end": "19:00"}],
            },
            {"weekday": 2, "intervals": [{"start": "12:00", "end": "20:00"}]},
        ]
    }
    week = await ok(await http.put(f"{API}/me/working-hours", json=hours, headers=master))
    assert [d["weekday"] for d in week["working_hours"]] == [0, 2]
    assert week["working_hours"][0]["intervals"][1] == {"start": "15:00", "end": "19:00"}
    overlap = {
        "days": [
            {
                "weekday": 1,
                "intervals": [{"start": "10:00", "end": "14:00"}, {"start": "13:00", "end": "15:00"}],
            }
        ]
    }
    assert problem(await http.put(f"{API}/me/working-hours", json=overlap, headers=master)) == (
        422,
        "invalid_schedule",
    )
    late = {"days": [{"weekday": 1, "intervals": [{"start": "10:00", "end": "25:00"}]}]}
    assert problem(await http.put(f"{API}/me/working-hours", json=late, headers=master)) == (
        422,
        "invalid_schedule",
    )
    empty = await http.put(f"{API}/me/working-hours", json={"days": []}, headers=master)
    assert problem(empty) == (409, "master_not_publishable")

    future = (date.today() + timedelta(days=10)).isoformat()
    past = (date.today() - timedelta(days=10)).isoformat()
    days = await ok(await http.put(f"{API}/me/days-off", json={"days": [future, past]}, headers=master))
    assert days["days_off"] == [future]

    rules = {
        "confirm_within_hours": 4,
        "change_deadline_hours": 24,
        "min_notice_minutes": 120,
        "horizon_days": 60,
        "slot_step_minutes": 15,
    }
    saved = await ok(await http.put(f"{API}/me/booking-rules", json=rules, headers=master))
    assert saved["booking_rules"] == rules
    assert saved["page"]["booking_rules"] == {"confirm_within_hours": 4, "change_deadline_hours": 24}
    wrong = await http.put(f"{API}/me/booking-rules", json={**rules, "slot_step_minutes": 7}, headers=master)
    assert problem(wrong) == (422, "invalid_booking_rules")


async def test_photos_and_avatar(http: httpx.AsyncClient, master: dict[str, str]) -> None:
    """Фото: загрузка, публичная ссылка с вечным кэшем, удаление; подделка формата — 422."""
    uploaded = await ok(
        await http.post(
            f"{API}/me/photos",
            files={"file": ("work.png", PNG, "image/png")},
            data={"alt": "Чистка лица"},
            headers=master,
        ),
        201,
    )
    photo = uploaded["page"]["photos"][-1]
    assert photo["url"].startswith(f"{API}/media/public/photos/")
    assert photo["alt"] == "Чистка лица"
    served = await http.get(photo["url"])
    assert (served.status_code, served.content, served.headers["content-type"]) == (200, PNG, "image/png")
    assert "immutable" in served.headers["cache-control"]

    fake = await http.post(
        f"{API}/me/photos", files={"file": ("x.png", b"not an image", "image/png")}, headers=master
    )
    assert problem(fake) == (422, "invalid_photo")
    text = await http.post(
        f"{API}/me/photos", files={"file": ("x.txt", b"hello", "text/plain")}, headers=master
    )
    assert problem(text) == (422, "invalid_photo")

    removed = await ok(await http.delete(f"{API}/me/photos/{photo['id']}", headers=master))
    assert all(p["id"] != photo["id"] for p in removed["page"]["photos"])
    assert (await http.get(photo["url"])).status_code == 404
    assert problem(await http.delete(f"{API}/me/photos/{photo['id']}", headers=master)) == (
        404,
        "photo_not_found",
    )
    assert (
        await http.get(f"{API}/media/public/voice/2026/10/x.webm")
    ).status_code == 404  # голосовые — не публичны

    avatar = await ok(
        await http.put(f"{API}/me/avatar", files={"file": ("me.png", PNG, "image/png")}, headers=master)
    )
    url = avatar["page"]["avatar_url"]
    assert (await http.get(url)).status_code == 200
    cleared = await ok(await http.delete(f"{API}/me/avatar", headers=master))
    assert cleared["page"]["avatar_url"] is None
    assert (await http.get(url)).status_code == 404


async def test_publication(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Скрыть и открыть страницу; черновик без услуг и часов не публикуется и объясняет почему."""
    hidden = await ok(await http.post(f"{API}/me/unpublish", headers=master))
    assert hidden["status"] == "draft"
    assert (await http.get(f"{API}/masters/{DEMO_SLUG}")).status_code == 404
    shown = await ok(await http.post(f"{API}/me/publish", headers=master))
    assert shown["status"] == "published"
    assert shown["published_at"] is not None
    assert (await http.get(f"{API}/masters/{DEMO_SLUG}")).status_code == 200

    await container.mediator.send(RegisterMaster("dana", "Дана", "Дана", "Даны", "Дане"))
    await container.mediator.send(AssignOwner("dana", "+77010010099"))
    dana = {"Authorization": f"Bearer {await login(http, container.mediator, 10099, '77010010099')}"}
    draft = await ok(await http.get(f"{API}/me/settings", headers=dana))
    assert draft["publish_blockers"] == ["Добавьте хотя бы одну услугу", "Задайте рабочие часы"]
    assert problem(await http.post(f"{API}/me/publish", headers=dana)) == (409, "master_not_publishable")
