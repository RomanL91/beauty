"""Поллер отложенных задач."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.shared.domain.clock import Clock
from beauty.shared.infrastructure.scheduling.backoff import BackoffStrategy, ExponentialBackoff
from beauty.shared.infrastructure.scheduling.registry import JobHandlerRegistry, UnknownJobKindError
from beauty.shared.infrastructure.scheduling.table import JobStatus, scheduled_jobs_table

logger = logging.getLogger(__name__)

_MAX_ERROR_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """Задача, взятая в работу."""

    id: UUID
    kind: str
    payload: Mapping[str, Any]
    attempts: int


class ScheduledJobPoller:
    """Забирает созревшие задачи и выполняет их с ограничением конкурентности.

    Цикл: вернуть в очередь задачи с истёкшей арендой → атомарно взять пачку
    (``UPDATE … WHERE id IN (SELECT … FOR UPDATE SKIP LOCKED) RETURNING``) →
    выполнить параллельно (``TaskGroup`` + ``Semaphore``) → записать исход. Захват
    и выполнение — разные транзакции: долгий обработчик не держит блокировку строки
    и соединение пула.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: JobHandlerRegistry,
        clock: Clock,
        batch_size: int = 100,
        poll_interval: float = 1.0,
        max_attempts: int = 5,
        lease: timedelta = timedelta(minutes=5),
        concurrency: int = 10,
        backoff: BackoffStrategy | None = None,
    ) -> None:
        """Собрать поллер."""
        self._session_factory = session_factory
        self._registry = registry
        self._clock = clock
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._max_attempts = max_attempts
        self._lease = lease
        self._semaphore = asyncio.Semaphore(concurrency)
        self._backoff = backoff or ExponentialBackoff()

    async def run(self, stop: asyncio.Event) -> None:
        """Опрашивать таблицу, пока не выставлен ``stop``."""
        while not stop.is_set():
            try:
                processed = await self.tick()
            except Exception:
                logger.exception("Поллер задач: ошибка итерации")
                processed = 0
            if processed < self._batch_size:
                try:
                    await asyncio.wait_for(stop.wait(), self._poll_interval)
                except TimeoutError:
                    continue

    async def tick(self) -> int:
        """Выполнить одну итерацию; вернуть число взятых задач."""
        jobs = await self._claim()
        if jobs:
            async with asyncio.TaskGroup() as group:
                for job in jobs:
                    group.create_task(self._execute(job), name=f"job:{job.kind}:{job.id}")
        return len(jobs)

    async def _claim(self) -> Sequence[ClaimedJob]:
        """Вернуть просроченные аренды и захватить пачку созревших задач."""
        table = scheduled_jobs_table
        now = self._clock.now()
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(table)
                .where(table.c.status == JobStatus.RUNNING.value, table.c.locked_until < now)
                .values(status=JobStatus.PENDING.value, locked_until=None, updated_at=now)
            )
            due = (
                select(table.c.id)
                .where(table.c.status == JobStatus.PENDING.value, table.c.due_at <= now)
                .order_by(table.c.due_at)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
                .scalar_subquery()
            )
            rows = await session.execute(
                update(table)
                .where(table.c.id.in_(due))
                .values(
                    status=JobStatus.RUNNING.value,
                    locked_until=now + self._lease,
                    attempts=table.c.attempts + 1,
                    updated_at=now,
                )
                .returning(table.c.id, table.c.kind, table.c.payload, table.c.attempts)
            )
            return [ClaimedJob(row.id, row.kind, row.payload, row.attempts) for row in rows]

    async def _execute(self, job: ClaimedJob) -> None:
        """Выполнить задачу и записать исход; исключения не выпускаются наружу."""
        async with self._semaphore:
            try:
                handler = self._registry.get(job.kind)
                await handler.handle(job.payload)
            except UnknownJobKindError as error:
                await self._finish(job, JobStatus.FAILED, f"Неизвестный вид задачи: {error}")
            except Exception as error:
                logger.exception("Задача %s (%s) упала", job.id, job.kind)
                await self._reschedule_or_fail(job, error)
            else:
                await self._finish(job, JobStatus.DONE, None)

    async def _reschedule_or_fail(self, job: ClaimedJob, error: Exception) -> None:
        """Вернуть задачу в очередь с задержкой или пометить проваленной."""
        message = f"{type(error).__name__}: {error}"[:_MAX_ERROR_LENGTH]
        if job.attempts >= self._max_attempts:
            await self._finish(job, JobStatus.FAILED, message)
            return
        await self._finish(job, JobStatus.PENDING, message, retry_in=self._backoff.delay(job.attempts))

    async def _finish(
        self, job: ClaimedJob, status: JobStatus, error: str | None, retry_in: timedelta | None = None
    ) -> None:
        """Записать исход, если задача всё ещё за нами (аренда не перехвачена)."""
        table = scheduled_jobs_table
        now = self._clock.now()
        values: dict[str, Any] = {
            "status": status.value,
            "locked_until": None,
            "last_error": error,
            "updated_at": now,
        }
        if retry_in is not None:
            values["due_at"] = now + retry_in
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(table)
                .where(table.c.id == job.id, table.c.status == JobStatus.RUNNING.value)
                .values(**values)
            )
