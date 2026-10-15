"""Tenancy на реальном PostgreSQL: маппинг агрегата, конкурентность, публичный HTTP API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DEMO_SLUG, DemoMasterSeeder
from beauty.contexts.tenancy.application.commands import (
    AddService,
    ArchiveService,
    PublishMaster,
    RegisterMaster,
    SetDaysOff,
    SetWeeklySchedule,
    UnpublishMaster,
    UpdateService,
)
from beauty.contexts.tenancy.application.errors import SlugTakenError
from beauty.contexts.tenancy.domain.master import Master
from beauty.contexts.tenancy.domain.value_objects import MasterStatus, ServiceDuration
from beauty.contexts.tenancy.infrastructure.uow import SqlAlchemyTenancyUnitOfWork
from beauty.entrypoints.api import ApiApplicationFactory
from beauty.shared.application.errors import ConcurrencyConflictError
from tests.integration.contract import assert_matches_schema

pytestmark = pytest.mark.integration

BASE = "https://api.beautiful.kz"
PREFIX = "/api/v1/masters"
ALMATY = ZoneInfo("Asia/Almaty")
UNKNOWN_SERVICE = "0192a0c0-0000-7000-8000-000000000000"


@pytest.fixture(scope="session")
def app(container: ApplicationContainer) -> FastAPI:
    """Приложение без realtime-моста."""
    return ApiApplicationFactory(container, enable_realtime_bridge=False).create()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP-клиент поверх ASGI."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
        yield http


def uow(container: ApplicationContainer) -> SqlAlchemyTenancyUnitOfWork:
    """Unit of Work поверх тестовой БД."""
    return SqlAlchemyTenancyUnitOfWork(container.session_factory, container.outbox_writer)


async def test_aggregate_roundtrip(container: ApplicationContainer) -> None:
    """Мастер с услугами, расписанием, правилами и выходными сохраняется и читается целиком."""
    master_id = await DemoMasterSeeder(container.mediator).seed()
    async with uow(container) as work:
        master = await work.masters.get(master_id)
        assert isinstance(master, Master)
        assert master.status is MasterStatus.PUBLISHED
        assert master.name_forms.dative == "Алисе"
        assert master.booking_rules.slot_step_minutes == 30
        assert master.schedule.hours_on(0)[1].start == time(15, 30)
        assert [s.duration for s in master.active_services][:2] == [ServiceDuration(40), ServiceDuration(60)]
        assert master.version >= 1

    async with container.engine.connect() as connection:
        routing = (
            (await connection.execute(text("SELECT routing_key FROM infra.outbox ORDER BY occurred_at")))
            .scalars()
            .all()
        )
    assert routing[0] == "tenancy.master.registered"
    assert "tenancy.master.published" in routing


async def test_seed_is_idempotent(container: ApplicationContainer) -> None:
    first = await DemoMasterSeeder(container.mediator).seed()
    second = await DemoMasterSeeder(container.mediator).seed()
    assert first == second
    async with container.engine.connect() as connection:
        services = (
            await connection.execute(text("SELECT count(*) FROM tenancy.master_services"))
        ).scalar_one()
    assert services == 4


async def test_optimistic_lock_on_concurrent_edits(container: ApplicationContainer) -> None:
    """Две единицы работы правят одного мастера: вторая получает конфликт версии."""
    master_id = await container.mediator.send(
        RegisterMaster("lock", "Мастер", "Мастер", "Мастера", "Мастеру")
    )
    async with uow(container) as first, uow(container) as second:
        a = await first.masters.get(master_id)
        b = await second.masters.get(master_id)
        assert a is not None
        assert b is not None
        now = datetime.now(ALMATY)
        a.add_service(container.id_generator.new(), "A", ServiceDuration(30), None, now)
        b.add_service(container.id_generator.new(), "B", ServiceDuration(30), None, now)
        await first.commit()
        with pytest.raises(ConcurrencyConflictError):
            await second.commit()


async def test_concurrent_registration_of_same_slug(container: ApplicationContainer) -> None:
    """Гонка двух регистраций: уникальный индекс + повтор медиатора → ровно один мастер."""
    results = await asyncio.gather(
        *(container.mediator.send(RegisterMaster("race", f"М{i}", "М", "М", "М")) for i in range(2)),
        return_exceptions=True,
    )
    created = [r for r in results if isinstance(r, UUID)]
    assert len(created) == 1
    assert [type(r) for r in results if not isinstance(r, UUID)] == [SlugTakenError]


async def test_public_page_matches_contract(
    client: httpx.AsyncClient, container: ApplicationContainer
) -> None:
    await DemoMasterSeeder(container.mediator).seed()
    response = await client.get(f"{PREFIX}/{DEMO_SLUG}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=60"
    body = response.json()
    assert_matches_schema(body, "MasterPage")
    assert body["name_forms"] == {"nominative": "Алиса", "genitive": "Алисы", "dative": "Алисе"}
    assert body["services"][0]["title"] == "Классический массаж спины"
    assert body["services"][0]["price"] == {"amount": 900_000, "currency": "KZT"}


async def test_slots_match_contract_and_rules(
    client: httpx.AsyncClient, container: ApplicationContainer
) -> None:
    master_id = await DemoMasterSeeder(container.mediator).seed()
    response = await client.get(f"{PREFIX}/{DEMO_SLUG}/slots", params={"limit": 5})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    items = response.json()["items"]
    assert len(items) == 5
    for item in items:
        assert_matches_schema(item, "Slot")
        start = datetime.fromisoformat(item["start"])
        assert start.utcoffset() == timedelta(hours=5)
        assert start > datetime.now(ALMATY) + timedelta(minutes=59)
        assert start.astimezone(ALMATY).weekday() != 6
    page = (await client.get(f"{PREFIX}/{DEMO_SLUG}")).json()
    shortest = min(page["services"], key=lambda s: s["duration_min"])
    assert {i["service_id"] for i in items} == {shortest["id"]}

    # Выходной на ближайшие дни — окон в этом окне поиска нет.
    tomorrow = (datetime.now(ALMATY) + timedelta(days=1)).date()
    await container.mediator.send(SetDaysOff(master_id, (tomorrow,)))
    window = {
        "from": datetime.combine(tomorrow, time(0), ALMATY).isoformat(),
        "to": datetime.combine(tomorrow, time(23, 59), ALMATY).isoformat(),
    }
    assert (await client.get(f"{PREFIX}/{DEMO_SLUG}/slots", params=window)).json()["items"] == []


async def test_service_changes_visible_on_page(
    client: httpx.AsyncClient, container: ApplicationContainer
) -> None:
    master_id = await container.mediator.send(RegisterMaster("dana", "Дана", "Дана", "Даны", "Дане"))
    first = await container.mediator.send(AddService(master_id, "Маникюр", 60, 700_000))
    second = await container.mediator.send(AddService(master_id, "Педикюр", 90, None))
    await container.mediator.send(SetWeeklySchedule(master_id, {0: ((time(10), time(18)),)}))
    await container.mediator.send(PublishMaster(master_id))
    await container.mediator.send(UpdateService(master_id, second, "Педикюр SPA", 75, 1_000_000))
    await container.mediator.send(ArchiveService(master_id, first))
    body = (await client.get(f"{PREFIX}/dana")).json()
    assert [(s["title"], s["duration_min"]) for s in body["services"]] == [("Педикюр SPA", 75)]

    await container.mediator.send(UnpublishMaster(master_id))
    assert (await client.get(f"{PREFIX}/dana")).status_code == 404


@pytest.mark.parametrize(
    ("path", "params", "status", "code"),
    [
        ("/nobody", {}, 404, "master_not_found"),
        ("/Not_A_Slug", {}, 404, "master_not_found"),
        (
            f"/{DEMO_SLUG}/slots",
            {"service": "0192a0c0-0000-7000-8000-000000000000"},
            404,
            "service_not_found",
        ),
        (f"/{DEMO_SLUG}/slots", {"limit": 0}, 422, "validation_error"),
        (f"/{DEMO_SLUG}/slots", {"from": "вчера"}, 422, "validation_error"),
        (f"/{DEMO_SLUG}/slots", {"from": "2026-10-20T10:00:00"}, 422, "invalid_slot_window"),
        (
            f"/{DEMO_SLUG}/slots",
            {"from": "2026-10-21T10:00:00+05:00", "to": "2026-10-20T10:00:00+05:00"},
            422,
            "invalid_slot_window",
        ),
    ],
)
async def test_errors_are_problem_json(
    client: httpx.AsyncClient,
    container: ApplicationContainer,
    path: str,
    params: dict[str, object],
    status: int,
    code: str,
) -> None:
    await DemoMasterSeeder(container.mediator).seed()
    response = await client.get(f"{PREFIX}{path}", params=params)
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    assert_matches_schema(body, "Problem")


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "http_404"
