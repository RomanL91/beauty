"""Задачи планировщика Conversations: чистка журнала ленты."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, ClassVar

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.conversations.infrastructure.tables import feed_events
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.scheduling.registry import JobHandler
from beauty.shared.infrastructure.scheduling.scheduler import JobRequest, JobScheduler

FEED_RETENTION = timedelta(hours=24)
PRUNE_EVERY = timedelta(hours=1)


class PruneFeedJob(JobHandler):
    """Удаляет события ленты старше суток и планирует следующий запуск.

    Ключ следующего запуска содержит его час: свой (выполняющийся) ключ планировщик
    не перезаписывает, а повторное планирование того же часа идемпотентно.
    """

    kind: ClassVar[str] = "conversations.prune_feed"

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Clock, ids: IdGenerator
    ) -> None:
        """Получить зависимости."""
        self._session_factory = session_factory
        self._clock = clock
        self._ids = ids

    @classmethod
    def request(cls, due_at: datetime) -> JobRequest:
        """Запуск на час ``due_at``."""
        return JobRequest(
            kind=cls.kind, dedup_key=f"conversations:prune-feed:{due_at:%Y%m%d%H}", due_at=due_at
        )

    async def handle(self, payload: Mapping[str, Any]) -> None:
        """Удалить старые события и запланировать следующую чистку."""
        now = self._clock.now()
        async with self._session_factory() as session, session.begin():
            await session.execute(delete(feed_events).where(feed_events.c.created_at < now - FEED_RETENTION))
            await JobScheduler(session, self._ids).schedule(self.request(now + PRUNE_EVERY))
