"""Админ-панель на реальном PostgreSQL: вход по логину и паролю, CSRF, перебор, отчёты по
контракту, мастера, блокировка клиента, администраторы и журнал действий."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DEMO_SLUG, DemoMasterSeeder
from beauty.contexts.admin.application.admins import CreateAdmin
from beauty.entrypoints.api import ApiApplicationFactory
from tests.integration.contract import assert_matches_schema
from tests.integration.helpers import login
from tests.integration.test_booking import BASE, new_client

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "correct horse battery"


@pytest.fixture(scope="session")
def app(container: ApplicationContainer) -> FastAPI:
    """Приложение без realtime-моста."""
    return ApiApplicationFactory(container, enable_realtime_bridge=False).create()


def client_of(app: FastAPI) -> httpx.AsyncClient:
    """Отдельный браузер (своя «банка» cookie)."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE)


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Браузер клиентов и мастеров."""
    async with client_of(app) as client:
        yield client


class Panel:
    """Браузер администратора: cookie сессии и CSRF-токен."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        """Ещё не вошёл."""
        self.http = http
        self.csrf = ""

    async def login(self, login: str, password: str = PASSWORD) -> httpx.Response:
        """Войти."""
        response = await self.http.post(
            f"{API}/admin/auth/login", json={"login": login, "password": password}
        )
        if response.status_code == 200:
            self.csrf = response.json()["csrf_token"]
        return response

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET и ответ (200)."""
        response = await self.http.get(f"{API}/admin{path}", params=params)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    async def send(self, method: str, path: str, body: Any = None, csrf: bool = True) -> httpx.Response:
        """Изменяющий запрос (с CSRF)."""
        headers = {"X-CSRF-Token": self.csrf} if csrf else {}
        return await self.http.request(method, f"{API}/admin{path}", json=body, headers=headers)


async def new_admin(container: ApplicationContainer, login: str) -> str:
    """Администратор с паролем ``PASSWORD``."""
    await container.mediator.send(CreateAdmin(None, login, f"Админ {login}", PASSWORD))
    return login


@pytest.fixture
async def panel(app: FastAPI, container: ApplicationContainer) -> AsyncIterator[Panel]:
    """Вошедший администратор."""
    async with client_of(app) as browser:
        panel = Panel(browser)
        name = await new_admin(container, f"owner-{uuid4().hex[:6]}")
        assert (await panel.login(name)).status_code == 200
        yield panel


def problem(response: httpx.Response) -> tuple[int, str]:
    """Статус и код problem+json."""
    return response.status_code, response.json()["code"]


async def test_login_session_csrf_and_logout(app: FastAPI, container: ApplicationContainer) -> None:
    """Неверный логин и пароль — одинаково; cookie httpOnly; без CSRF изменения запрещены."""
    name = await new_admin(container, f"boss-{uuid4().hex[:6]}")
    async with client_of(app) as browser:
        panel = Panel(browser)
        assert problem(await panel.login(name, "wrong password!")) == (401, "invalid_credentials")
        assert problem(await panel.login("nobody-here", PASSWORD)) == (401, "invalid_credentials")
        assert problem(await browser.get(f"{API}/admin/dashboard")) == (401, "admin_unauthorized")

        response = await panel.login(f"  {name.upper()} ")
        assert response.status_code == 200, response.text
        assert_matches_schema(response.json(), "AdminSession")
        cookie = response.headers["set-cookie"]
        assert "bk_admin=" in cookie
        assert "HttpOnly" in cookie
        assert "Path=/api/v1/admin" in cookie
        assert "SameSite=strict" in cookie
        me = await panel.get("/auth/me")
        assert (me["admin"]["login"], me["csrf_token"]) == (name, panel.csrf)

        assert problem(await panel.send("POST", "/auth/logout", csrf=False)) == (403, "csrf_failed")
        panel.csrf = "forged"
        assert problem(await panel.send("POST", "/auth/logout")) == (403, "csrf_failed")
        panel.csrf = me["csrf_token"]
        assert (await panel.send("POST", "/auth/logout")).status_code == 204
        assert (await browser.get(f"{API}/admin/auth/me")).status_code == 401


async def test_brute_force_locks_the_account(app: FastAPI, container: ApplicationContainer) -> None:
    """5 неверных паролей — вход закрыт даже с верным паролем."""
    name = await new_admin(container, f"guard-{uuid4().hex[:6]}")
    async with client_of(app) as browser:
        panel = Panel(browser)
        statuses = [(await panel.login(name, f"wrong-{i}-password")).status_code for i in range(5)]
        assert statuses == [401, 401, 401, 401, 429]
        assert problem(await panel.login(name)) == (429, "admin_locked")


async def test_reports_match_the_contract(
    panel: Panel, http: httpx.AsyncClient, container: ApplicationContainer
) -> None:
    """Сводка, мастера, карточка, клиенты, агент, система — по схемам контракта."""
    await DemoMasterSeeder(container.mediator).seed("+77010020001")
    await new_client(http, container, 20011)
    dashboard = await panel.get("/dashboard")
    assert_matches_schema(dashboard, "AdminDashboard")
    assert len(dashboard["days"]) == 30
    assert dashboard["totals"]["masters"] >= 1

    masters = (await panel.get("/masters", q=DEMO_SLUG))["items"]
    alisa = next(m for m in masters if m["slug"] == DEMO_SLUG)
    assert_matches_schema(alisa, "AdminMasterRow")
    assert (alisa["status"], alisa["agent"], alisa["owner_phone"]) == (
        "published",
        "not_connected",
        "+77010020001",
    )
    assert await panel.get("/masters", q="нет-такого") == {"items": []}

    detail = await panel.get(f"/masters/{alisa['id']}")
    assert_matches_schema(detail, "AdminMasterDetail")
    assert detail["page"]["slug"] == DEMO_SLUG
    assert detail["agent_command"] == 'docker compose run --rm agent-setup "beauty agent provision alisa"'
    assert detail["stats"]["conversations"] >= 1

    clients = await panel.get("/clients", q="7701002", limit=10)
    assert all(c["phone"].startswith("+7701002") for c in clients["items"])
    for row in clients["items"]:
        assert_matches_schema(row, "AdminClientRow")
    for path, schema in (("/agent", "AdminAgentReport"), ("/system", "AdminSystem")):
        assert_matches_schema(await panel.get(path), schema)
    system = await panel.get("/system")
    assert system["database"] is True


async def test_create_master_owner_and_publication(
    panel: Panel, http: httpx.AsyncClient, container: ApplicationContainer
) -> None:
    """Новый мастер — черновик с владельцем: кабинет открывается его телефону; публикация — по правилам."""
    slug = f"dana-{uuid4().hex[:6]}"
    body = {
        "slug": slug,
        "display_name": "Дана Ахметова",
        "name_forms": {"nominative": "Дана", "genitive": "Даны", "dative": "Дане"},
        "specialty": "Маникюр",
        "timezone": "Asia/Almaty",
        "owner_phone": "+77010020101",
    }
    created = await panel.send("POST", "/masters", body)
    assert created.status_code == 201, created.text
    master = created.json()
    assert_matches_schema(master, "AdminMasterDetail")
    assert (master["status"], master["specialty"], master["owner_phone"]) == (
        "draft",
        "Маникюр",
        "+77010020101",
    )
    assert master["publish_blockers"] == ["Добавьте хотя бы одну услугу", "Задайте рабочие часы"]
    assert problem(await panel.send("POST", "/masters", body)) == (409, "slug_taken")

    token = await login(http, container.mediator, 20101, "77010020101")
    me = await http.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
    assert (me.status_code, me.json()["slug"]) == (200, slug)

    moved = await panel.send("PUT", f"/masters/{master['id']}/owner", {"phone": "+77010020102"})
    assert moved.json()["owner_phone"] == "+77010020102"
    blocked = await panel.send("PUT", f"/masters/{master['id']}/publication", {"published": True})
    assert problem(blocked) == (409, "master_not_publishable")
    no_agent = await panel.send("PUT", f"/masters/{master['id']}/agent", {"enabled": True})
    assert problem(no_agent) == (404, "agent_not_provisioned")
    assert problem(await panel.send("PUT", f"/masters/{uuid4()}/publication", {"published": False})) == (
        404,
        "master_not_found",
    )

    log = (await panel.get("/audit", limit=5))["items"]
    assert [(e["action"], e["target"]) for e in log[:2]] == [
        ("master.owner_changed", slug),
        ("master.created", slug),
    ]
    assert log[0]["summary"] == "Владелец: +77010020101 → +77010020102"


async def test_blocked_client_cannot_sign_in(
    panel: Panel, app: FastAPI, http: httpx.AsyncClient, container: ApplicationContainer
) -> None:
    """Блокировка отзывает сессии: refresh — 403; снова войти нельзя; разблокировка возвращает вход."""
    await login(http, container.mediator, 20201, "77010020201")  # у браузера есть refresh-cookie
    found = (await panel.get("/clients", q="77010020201"))["items"]
    (client,) = [c for c in found if c["phone"] == "+77010020201"] or [None]
    assert client is not None

    blocked = await panel.send("PUT", f"/clients/{client['id']}/block", {"blocked": True, "reason": "Спам"})
    assert (blocked.json()["blocked"], blocked.json()["blocked_reason"]) == (True, "Спам")
    refresh = await http.post(f"{API}/auth/session/refresh")
    assert refresh.status_code in (401, 403)
    async with client_of(app) as other:
        with pytest.raises(KeyError):  # обмен входа на сессию — 403 account_blocked, токена нет
            await login(other, container.mediator, 20201, "77010020201")
    assert (await panel.get("/dashboard"))["totals"]["blocked_clients"] >= 1

    unblocked = await panel.send("PUT", f"/clients/{client['id']}/block", {"blocked": False})
    assert unblocked.json()["blocked"] is False
    async with client_of(app) as other:
        assert await login(other, container.mediator, 20201, "77010020201")
    actions = [e["action"] for e in (await panel.get("/audit", limit=3))["items"]]
    assert actions[:2] == ["client.unblocked", "client.blocked"]


async def test_admins_management(panel: Panel, app: FastAPI, container: ApplicationContainer) -> None:
    """Добавить, повтор логина, себя не отключить, отключённый теряет сессию, смена своего пароля."""
    login_name = f"helper-{uuid4().hex[:6]}"
    created = await panel.send(
        "POST", "/admins", {"login": login_name, "display_name": "Помощник", "password": PASSWORD}
    )
    assert created.status_code == 201, created.text
    helper = created.json()
    assert_matches_schema(helper, "AdminAccount")
    duplicate = await panel.send(
        "POST", "/admins", {"login": login_name, "display_name": "X", "password": PASSWORD}
    )
    assert problem(duplicate) == (409, "admin_login_taken")
    me = await panel.get("/auth/me")
    assert problem(await panel.send("PATCH", f"/admins/{me['admin']['id']}", {"active": False})) == (
        409,
        "cannot_disable_self",
    )

    async with client_of(app) as browser:
        other = Panel(browser)
        assert (await other.login(login_name)).status_code == 200
        disabled = await panel.send("PATCH", f"/admins/{helper['id']}", {"active": False})
        assert disabled.json()["active"] is False
        assert (await browser.get(f"{API}/admin/auth/me")).status_code == 401
        assert problem(await other.login(login_name)) == (401, "invalid_credentials")

    wrong = await panel.send(
        "POST", "/auth/password", {"current_password": "nope", "new_password": "brand new password"}
    )
    assert problem(wrong) == (403, "wrong_password")
    short = await panel.send(
        "POST", "/auth/password", {"current_password": PASSWORD, "new_password": "short"}
    )
    assert short.status_code == 422
    changed = await panel.send(
        "POST", "/auth/password", {"current_password": PASSWORD, "new_password": "brand new password"}
    )
    assert changed.status_code == 204
    assert (await panel.get("/auth/me"))["admin"]["id"] == me["admin"]["id"]  # своя сессия жива
    listed = await panel.get("/admins")
    assert any(a["login"] == login_name and not a["active"] for a in listed["items"])
    audit = await panel.get("/audit", limit=100)
    for entry in audit["items"]:
        assert_matches_schema(entry, "AdminAuditEntry")
    assert {"admin.created", "admin.updated", "admin.password_changed"} <= {
        e["action"] for e in audit["items"]
    }
