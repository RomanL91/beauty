"""Relay: перенос событий из outbox в брокер."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy import Row, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.shared.domain.clock import Clock
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.outbox.table import outbox_table

logger = logging.getLogger(__name__)


class EventPublisher(ABC):
    """Порт публикации конверта в брокер с подтверждением."""

    @abstractmethod
    async def publish(self, envelope: EventEnvelope) -> None:
        """Опубликовать и дождаться publisher confirm (иначе — исключение)."""


class WakeupSource(Protocol):
    """Источник пробуждения relay (LISTEN/NOTIFY или таймер)."""

    async def wait(self, timeout: float) -> bool:
        """Ждать сигнала не дольше ``timeout`` секунд."""
        ...


class OutboxRelay:
    """Публикует неопубликованные записи outbox пачками.

    Пачка забирается ``SELECT … FOR UPDATE SKIP LOCKED`` в отдельной транзакции:
    параллельные relay берут разные строки. Внутри пачки публикация последовательная —
    это сохраняет порядок событий одного агрегата в брокере (параллельный publish
    мог бы переставить их). Если публикация упала посередине, помечаются только
    подтверждённые записи, остальные вернутся в следующей итерации.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: EventPublisher,
        wakeup: WakeupSource,
        clock: Clock,
        batch_size: int = 200,
        idle_poll_interval: float = 5.0,
        error_backoff: float = 1.0,
    ) -> None:
        """Собрать relay из зависимостей."""
        self._session_factory = session_factory
        self._publisher = publisher
        self._wakeup = wakeup
        self._clock = clock
        self._batch_size = batch_size
        self._idle_poll_interval = idle_poll_interval
        self._error_backoff = error_backoff

    async def run(self, stop: asyncio.Event) -> None:
        """Крутить цикл, пока не выставлен ``stop``."""
        while not stop.is_set():
            try:
                published = await self.relay_batch()
            except Exception:
                logger.exception("Outbox relay: ошибка итерации")
                await asyncio.sleep(self._error_backoff)
                continue
            if published < self._batch_size:
                await self._wakeup.wait(self._idle_poll_interval)

    async def relay_batch(self) -> int:
        """Опубликовать одну пачку; вернуть число опубликованных событий."""
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.execute(
                    select(outbox_table)
                    .where(outbox_table.c.published_at.is_(None))
                    .order_by(outbox_table.c.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if not rows:
                return 0
            published_ids = await self._publish(rows)
            if published_ids:
                await session.execute(
                    update(outbox_table)
                    .where(outbox_table.c.id.in_(published_ids))
                    .values(published_at=self._clock.now())
                )
            return len(published_ids)

    async def _publish(self, rows: Sequence[Row[tuple[object, ...]]]) -> list[UUID]:
        """Публиковать по порядку до первой ошибки."""
        published: list[UUID] = []
        for row in rows:
            envelope = EventEnvelope(
                message_id=row.id,
                routing_key=row.routing_key,
                event_type=row.event_type,
                event_version=row.event_version,
                occurred_at=row.occurred_at,
                payload=row.payload,
            )
            try:
                await self._publisher.publish(envelope)
            except Exception:
                logger.exception("Outbox relay: не удалось опубликовать %s", row.id)
                break
            published.append(row.id)
        return published
