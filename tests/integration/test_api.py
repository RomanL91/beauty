"""Сквозной сценарий входа через HTTP API (FastAPI + реальная БД)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from beauty.bootstrap.container import ApplicationContainer
from beauty.contexts.identity.infrastructure.realtime import ChallengeTopic
from beauty.entrypoints.api import ApiApplicationFactory
from tests.integration.contract import assert_matches_schema
from tests.integration.helpers import BotSimulator

pytestmark = pytest.mark.integration

BASE = "https://api.beautiful.kz"
PREFIX = "/api/v1/auth"


@pytest.fixture(scope="session")
def app(container: ApplicationContainer) -> FastAPI:
    """Приложение без realtime-моста (брокер в тестах не нужен)."""
    return ApiApplicationFactory(container, enable_realtime_bridge=False).create()


@pytest.fixture
async def browser(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """«Браузер» со своим хранилищем cookie."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        yield client


def sse_statuses(body: str) -> list[str]:
    """Статусы из потока SSE."""
    return [json.loads(line[6:])["status"] for line in body.splitlines() if line.startswith("data: ")]


async def test_full_login_flow(browser: httpx.AsyncClient, container: ApplicationContainer) -> None:
    """Браузер начинает вход → бот подтверждает → браузер получает сессию → refresh → logout."""
    started = await browser.post(f"{PREFIX}/telegram/challenges")
    assert started.status_code == 201
    body = started.json()
    challenge_id = body["challenge_id"]
    assert "bk_auth_challenge" in browser.cookies
    assert "browser_secret" not in body

    status = await browser.get(f"{PREFIX}/telegram/challenges/{challenge_id}")
    assert status.json()["status"] == "pending"

    bot = BotSimulator(container.mediator)
    await bot.confirm(body["deep_link"], body["confirmation_code"], telegram_user=1001)
    await bot.share_contact(1001, "77011234567")

    events = await browser.get(f"{PREFIX}/telegram/challenges/{challenge_id}/events")
    assert events.headers["content-type"].startswith("text/event-stream")
    assert sse_statuses(events.text) == ["completed"]

    session = await browser.post(f"{PREFIX}/telegram/challenges/{challenge_id}/session")
    assert session.status_code == 200, session.text
    access = session.json()["access_token"]
    assert container.identity.access_token_verifier.verify(access).account_id is not None
    assert "bk_refresh" in browser.cookies
    assert "bk_auth_challenge" not in browser.cookies

    again = await browser.post(f"{PREFIX}/telegram/challenges/{challenge_id}/session")
    assert again.status_code == 404

    old_refresh = browser.cookies["bk_refresh"]
    refreshed = await browser.post(f"{PREFIX}/session/refresh")
    assert refreshed.status_code == 200
    assert browser.cookies["bk_refresh"] != old_refresh

    logout = await browser.post(f"{PREFIX}/session/logout")
    assert logout.status_code == 204
    assert "bk_refresh" not in browser.cookies
    assert (await browser.post(f"{PREFIX}/session/refresh")).status_code == 401


async def test_other_browser_cannot_read_or_take_session(app: FastAPI, browser: httpx.AsyncClient) -> None:
    """Чужой браузер (без cookie) не видит вход и не может забрать сессию."""
    started = (await browser.post(f"{PREFIX}/telegram/challenges")).json()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as stranger:
        assert (
            await stranger.get(f"{PREFIX}/telegram/challenges/{started['challenge_id']}")
        ).status_code == 404
        taken = await stranger.post(f"{PREFIX}/telegram/challenges/{started['challenge_id']}/session")
        assert taken.status_code == 404


async def test_stolen_refresh_token_revokes_session(app: FastAPI, container: ApplicationContainer) -> None:
    """Вор с копией старого refresh-токена: после окна снисхождения сессия отзывается у обоих."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as owner:
        started = (await owner.post(f"{PREFIX}/telegram/challenges")).json()
        bot = BotSimulator(container.mediator)
        await bot.confirm(started["deep_link"], started["confirmation_code"], telegram_user=2002)
        await bot.share_contact(2002, "77012222222")
        await owner.post(f"{PREFIX}/telegram/challenges/{started['challenge_id']}/session")
        stolen = owner.cookies["bk_refresh"]
        assert (await owner.post(f"{PREFIX}/session/refresh")).status_code == 200

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as thief:
            thief.cookies.set("bk_refresh", stolen, domain="api.beautiful.kz", path=f"{PREFIX}/session")
            response = await thief.post(f"{PREFIX}/session/refresh")
            assert response.status_code == 200, "в окне снисхождения повтор выглядит как вторая вкладка"
            assert "bk_refresh" not in response.cookies

        async with container.engine.begin() as connection:
            await connection.execute(
                text("UPDATE identity.client_sessions SET rotated_at = rotated_at - interval '5 minutes'")
            )
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as thief:
            thief.cookies.set("bk_refresh", stolen, domain="api.beautiful.kz", path=f"{PREFIX}/session")
            response = await thief.post(f"{PREFIX}/session/refresh")
            assert response.status_code == 401
            assert response.headers["content-type"] == "application/problem+json"
            assert response.json()["code"] == "session_reuse_detected"
            assert_matches_schema(response.json(), "Problem")
        assert (await owner.post(f"{PREFIX}/session/refresh")).status_code == 401


async def test_sse_reacts_to_realtime_event(
    browser: httpx.AsyncClient, container: ApplicationContainer
) -> None:
    """Событие из брокера (через хаб) мгновенно доходит до SSE-подписчика."""
    started = (await browser.post(f"{PREFIX}/telegram/challenges")).json()
    challenge_id = started["challenge_id"]
    stream = asyncio.create_task(browser.get(f"{PREFIX}/telegram/challenges/{challenge_id}/events"))
    await asyncio.sleep(0.1)

    bot = BotSimulator(container.mediator)
    await bot.confirm(started["deep_link"], started["confirmation_code"], telegram_user=3003)
    await bot.share_contact(3003, "77013333333")
    container.realtime_hub.publish(ChallengeTopic.for_challenge(challenge_id), {"status": "completed"})

    began = time.monotonic()
    response = await asyncio.wait_for(stream, timeout=5)
    assert time.monotonic() - began < 2
    statuses = sse_statuses(response.text)
    assert statuses[0] == "pending"
    assert statuses[-1] == "completed"


async def test_wrong_code_is_visible_to_browser(
    browser: httpx.AsyncClient, container: ApplicationContainer
) -> None:
    """Отклонённый вход браузер видит как rejected."""
    started = (await browser.post(f"{PREFIX}/telegram/challenges")).json()
    wrong = "10" if started["confirmation_code"] != "10" else "11"
    await BotSimulator(container.mediator).confirm(started["deep_link"], wrong, telegram_user=4004)
    status = await browser.get(f"{PREFIX}/telegram/challenges/{started['challenge_id']}")
    assert status.json()["status"] == "rejected"
