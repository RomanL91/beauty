"""Охрана идемпотентности консьюмеров."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from beauty.shared.infrastructure.db.scope import TransactionScope
from beauty.shared.infrastructure.inbox.table import inbox_table
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope


class InboxGuard:
    """Регистрирует обработку сообщения консьюмером."""

    async def claim(self, session: AsyncSession, consumer: str, message_id: UUID) -> bool:
        """Вернуть ``True``, если сообщение ещё не обрабатывалось этим консьюмером.

        ``INSERT … ON CONFLICT DO NOTHING RETURNING`` атомарен: при гонке двух
        доставок одного сообщения вторая транзакция дождётся первой и получит пустой
        результат.
        """
        statement = (
            insert(inbox_table)
            .values(consumer=consumer, message_id=message_id)
            .on_conflict_do_nothing(index_elements=[inbox_table.c.consumer, inbox_table.c.message_id])
            .returning(inbox_table.c.message_id)
        )
        return (await session.execute(statement)).scalar_one_or_none() is not None


class InboxIdempotentHandler(IntegrationEventHandler):
    """Декоратор обработчика: inbox + амбиентная транзакция.

    Открывает ``TransactionScope``, отмечает сообщение в inbox и вызывает вложенный
    обработчик. Unit of Work команд, вызванных обработчиком через медиатор,
    присоединяются к этой транзакции — отметка в inbox и изменения либо сохраняются
    вместе, либо откатываются вместе.
    """

    def __init__(
        self, inner: IntegrationEventHandler, scope: TransactionScope, guard: InboxGuard, consumer: str
    ) -> None:
        """Обернуть обработчик."""
        self._inner = inner
        self._scope = scope
        self._guard = guard
        self._consumer = consumer

    async def handle(self, envelope: EventEnvelope) -> None:
        """Обработать сообщение ровно один раз (с точки зрения эффектов в БД)."""
        async with self._scope.begin() as session:
            if not await self._guard.claim(session, self._consumer, envelope.message_id):
                return
            await self._inner.handle(envelope)


class InboxClaimFirstHandler(IntegrationEventHandler):
    """Inbox без общей транзакции: отметка о доставке — до обработки (at-most-once).

    Для долгих обработчиков, которые ходят во внешние системы (ход ИИ-агента до минуты):
    держать транзакцию открытой всё это время нельзя, а промежуточные записи (тикет хода)
    должны быть видны другим процессам сразу. Повторная доставка уже отмеченного события
    не обрабатывается; если процесс упадёт посреди обработки, событие не повторится —
    обработчик сам должен оставлять безопасное состояние (вопрос клиента ждёт мастера).
    """

    def __init__(
        self,
        inner: IntegrationEventHandler,
        session_factory: Callable[[], AsyncSession],
        guard: InboxGuard,
        consumer: str,
    ) -> None:
        """Обернуть обработчик."""
        self._inner = inner
        self._session_factory = session_factory
        self._guard = guard
        self._consumer = consumer

    async def handle(self, envelope: EventEnvelope) -> None:
        """Отметить и обработать."""
        async with self._session_factory() as session, session.begin():
            claimed = await self._guard.claim(session, self._consumer, envelope.message_id)
        if claimed:
            await self._inner.handle(envelope)
