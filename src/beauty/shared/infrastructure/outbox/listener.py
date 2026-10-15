"""Пробуждение relay через ``LISTEN/NOTIFY`` PostgreSQL."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import asyncpg
from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)


class PostgresNotificationListener:
    """Держит отдельное соединение asyncpg с ``LISTEN`` на канале.

    Колбэк asyncpg вызывается в event loop синхронно, поэтому он только выставляет
    ``asyncio.Event`` — без ввода-вывода. Relay ждёт этот флаг вместе с таймаутом:
    таймаут страхует от потерянных уведомлений (NOTIFY не хранится, если в момент
    отправки слушателя не было), уведомление убирает задержку опроса.
    """

    def __init__(self, sqlalchemy_url: str, channel: str, reconnect_delay: float = 2.0) -> None:
        """Преобразовать URL SQLAlchemy в DSN asyncpg и запомнить канал."""
        url = make_url(sqlalchemy_url).set(drivername="postgresql")
        self._dsn = url.render_as_string(hide_password=False)
        self._channel = channel
        self._reconnect_delay = reconnect_delay
        self._signal = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Запустить фоновую задачу поддержания соединения."""
        if self._task is None:
            self._task = asyncio.create_task(self._maintain(), name=f"pg-listen:{self._channel}")

    async def stop(self) -> None:
        """Остановить фоновую задачу."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def wait(self, timeout: float) -> bool:
        """Дождаться уведомления или таймаута; ``True`` — пришло уведомление."""
        try:
            await asyncio.wait_for(self._signal.wait(), timeout)
        except TimeoutError:
            return False
        finally:
            self._signal.clear()
        return True

    async def _maintain(self) -> None:
        """Переподключаться к БД, пока задача не отменена."""
        while True:
            connection: asyncpg.Connection | None = None
            try:
                connection = await asyncpg.connect(self._dsn)
                lost = asyncio.Event()
                connection.add_termination_listener(lambda _conn, event=lost: event.set())
                await connection.add_listener(self._channel, self._on_notify)
                self._signal.set()
                await lost.wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("LISTEN %s: соединение потеряно, переподключение", self._channel)
            finally:
                if connection is not None and not connection.is_closed():
                    await connection.close()
            await asyncio.sleep(self._reconnect_delay)

    def _on_notify(self, *_: Any) -> None:
        """Колбэк asyncpg: только поднять флаг."""
        self._signal.set()
