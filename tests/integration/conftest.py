"""Фикстуры интеграционных тестов.

На сессию создаётся отдельная БД, на неё накатываются миграции Alembic (те же, что в
проде), перед каждым тестом таблицы очищаются. URL сервера задаётся переменной
``BEAUTY_TEST_DATABASE_URL`` (например,
``postgresql+asyncpg://postgres@localhost:5432/postgres``); без неё тесты пропускаются.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url

from beauty.bootstrap.container import ApplicationContainer
from beauty.shared.infrastructure.config import (
    AuthSettings,
    DatabaseSettings,
    HttpSettings,
    Settings,
    StorageSettings,
)

ROOT = Path(__file__).resolve().parents[2]
SERVER_URL = os.environ.get("BEAUTY_TEST_DATABASE_URL")

pytestmark = pytest.mark.integration


def _asyncpg_dsn(url: str) -> str:
    """DSN asyncpg из URL SQLAlchemy."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
async def database_url() -> AsyncIterator[str]:
    """Свежая БД с применёнными миграциями."""
    if not SERVER_URL:
        pytest.skip("BEAUTY_TEST_DATABASE_URL не задан")
    name = f"beauty_it_{os.getpid()}"
    admin = await asyncpg.connect(_asyncpg_dsn(SERVER_URL))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    url = make_url(SERVER_URL).set(database=name).render_as_string(hide_password=False)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    await asyncio.to_thread(command.upgrade, config, "head")
    yield url
    admin = await asyncpg.connect(_asyncpg_dsn(SERVER_URL))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.fixture(scope="session")
async def container(
    database_url: str, tmp_path_factory: pytest.TempPathFactory
) -> AsyncIterator[ApplicationContainer]:
    """Контейнер приложения поверх тестовой БД (SSE-потоки — короткие)."""
    settings = Settings(
        database=DatabaseSettings(url=database_url, pool_size=5, max_overflow=5),
        auth=AuthSettings(cookie_secure=True),
        http=HttpSettings(sse_poll_interval=0.2, sse_max_duration=0.6),
        storage=StorageSettings(root=str(tmp_path_factory.mktemp("files"))),
    )
    container = ApplicationContainer(settings, process_name="beauty-tests")
    _ = container.mediator
    yield container
    await container.aclose()


@pytest.fixture(autouse=True)
async def clean_database(container: ApplicationContainer) -> None:
    """Очистить данные перед тестом."""
    async with container.engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE identity.client_sessions, identity.auth_challenges, identity.client_accounts, "
                "tenancy.master_services, tenancy.masters, booking.appointments, "
                "conversations.feed_events, conversations.messages, conversations.conversations, "
                "infra.outbox, infra.inbox, infra.scheduled_jobs CASCADE"
            )
        )
