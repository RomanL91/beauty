"""Амбиентная транзакция (паттерн Transaction Scope).

Консьюмеру брокера нужно атомарно: отметить сообщение в inbox и выполнить команду,
которую он вызывает через медиатор. Команда открывает свой Unit of Work и о консьюмере
ничего не знает. ``TransactionScope`` кладёт сессию в ``ContextVar``; Unit of Work,
открытый внутри scope, присоединяется к ней через SAVEPOINT, а реальный COMMIT делает
владелец scope.

Тонкость event loop: ``ContextVar`` копируется в задачи, созданные внутри scope
(``asyncio.create_task``, ``TaskGroup``). ``AsyncSession`` нельзя использовать из
нескольких корутин одновременно, поэтому присоединиться к scope может только та же
задача, что его открыла; дочерние задачи получат собственную сессию.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(frozen=True, slots=True)
class _AmbientTransaction:
    """Сессия scope и задача-владелец."""

    session: AsyncSession
    owner: asyncio.Task[object] | None


_ambient: ContextVar[_AmbientTransaction | None] = ContextVar("beauty_ambient_tx", default=None)


class TransactionScope:
    """Открывает амбиентную транзакцию, к которой присоединяются Unit of Work."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Запомнить фабрику сессий."""
        self._session_factory = session_factory

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        """Открыть транзакцию; COMMIT — при нормальном выходе, ROLLBACK — при исключении."""
        if self.joinable_session() is not None:
            raise RuntimeError("Вложенный TransactionScope в той же задаче не поддерживается")
        async with self._session_factory() as session, session.begin():
            token = _ambient.set(_AmbientTransaction(session, asyncio.current_task()))
            try:
                yield session
            finally:
                _ambient.reset(token)

    @staticmethod
    def joinable_session() -> AsyncSession | None:
        """Сессия scope, если к ней можно присоединиться из текущей задачи."""
        ambient = _ambient.get()
        if ambient is None or ambient.owner is not asyncio.current_task():
            return None
        return ambient.session
