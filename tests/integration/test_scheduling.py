"""Отложенные задачи: планирование, перенос, отмена, выполнение, повторы, аренда."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, ClassVar

import pytest
from sqlalchemy import select, update

from beauty.bootstrap.container import ApplicationContainer
from beauty.shared.infrastructure.scheduling.backoff import ExponentialBackoff
from beauty.shared.infrastructure.scheduling.poller import ScheduledJobPoller
from beauty.shared.infrastructure.scheduling.registry import JobHandler, JobHandlerRegistry
from beauty.shared.infrastructure.scheduling.scheduler import JobRequest, JobScheduler
from beauty.shared.infrastructure.scheduling.table import scheduled_jobs_table as jobs
from tests.fakes import FrozenClock

pytestmark = pytest.mark.integration


class RecordingHandler(JobHandler):
    """Запоминает выполненные задачи; может падать."""

    kind: ClassVar[str] = "test.remind"

    def __init__(self, fail: bool = False) -> None:
        self.payloads: list[Mapping[str, Any]] = []
        self._fail = fail

    async def handle(self, payload: Mapping[str, Any]) -> None:
        if self._fail:
            raise RuntimeError("SMTP недоступен")
        self.payloads.append(payload)


async def schedule(container: ApplicationContainer, *requests: JobRequest) -> None:
    """Запланировать задачи в отдельной транзакции."""
    async with container.session_factory() as session, session.begin():
        scheduler = JobScheduler(session)
        for request in requests:
            await scheduler.schedule(request)


async def job_rows(container: ApplicationContainer) -> dict[str, Any]:
    """Строки задач по dedup_key."""
    async with container.session_factory() as session:
        rows = (await session.execute(select(jobs))).all()
    return {row.dedup_key: row for row in rows}


def poller(container: ApplicationContainer, handler: JobHandler, clock: FrozenClock) -> ScheduledJobPoller:
    """Поллер с одним обработчиком."""
    return ScheduledJobPoller(
        container.session_factory,
        JobHandlerRegistry((handler,)),
        clock,
        max_attempts=2,
        lease=timedelta(minutes=1),
        backoff=ExponentialBackoff(timedelta(seconds=30)),
    )


async def test_reschedule_and_cancel(container: ApplicationContainer, clock: FrozenClock) -> None:
    """Повторное планирование переносит задачу; отмена по префиксу касается только своих."""
    now = clock.now()
    await schedule(
        container,
        JobRequest("test.remind", "reminder:a1:24h", now + timedelta(hours=1), {"n": 1}),
        JobRequest("test.remind", "reminder:a1:2h", now + timedelta(hours=2)),
        JobRequest("test.remind", "reminder:a10:2h", now + timedelta(hours=2)),
    )
    await schedule(
        container, JobRequest("test.remind", "reminder:a1:24h", now + timedelta(hours=3), {"n": 2})
    )
    rows = await job_rows(container)
    assert len(rows) == 3
    assert rows["reminder:a1:24h"].due_at == now + timedelta(hours=3)
    assert rows["reminder:a1:24h"].payload == {"n": 2}

    async with container.session_factory() as session, session.begin():
        await JobScheduler(session).cancel_by_prefix("reminder:a1:")
    statuses = {key: row.status for key, row in (await job_rows(container)).items()}
    assert statuses == {
        "reminder:a1:24h": "cancelled",
        "reminder:a1:2h": "cancelled",
        "reminder:a10:2h": "pending",
    }


async def test_poller_runs_only_due_jobs(container: ApplicationContainer, clock: FrozenClock) -> None:
    """Выполняются только созревшие задачи."""
    now = clock.now()
    await schedule(
        container,
        JobRequest("test.remind", "due", now - timedelta(seconds=1), {"x": 1}),
        JobRequest("test.remind", "later", now + timedelta(hours=1)),
    )
    handler = RecordingHandler()
    assert await poller(container, handler, clock).tick() == 1
    assert handler.payloads == [{"x": 1}]
    statuses = {key: row.status for key, row in (await job_rows(container)).items()}
    assert statuses == {"due": "done", "later": "pending"}


async def test_failures_retry_then_fail(container: ApplicationContainer, clock: FrozenClock) -> None:
    """Упавшая задача переносится с задержкой, после лимита — failed."""
    await schedule(container, JobRequest("test.remind", "flaky", clock.now()))
    failing = poller(container, RecordingHandler(fail=True), clock)
    await failing.tick()
    row = (await job_rows(container))["flaky"]
    assert (row.status, row.attempts) == ("pending", 1)
    assert row.due_at == clock.now() + timedelta(seconds=30)
    assert "SMTP" in row.last_error

    clock.advance(timedelta(seconds=31))
    await failing.tick()
    row = (await job_rows(container))["flaky"]
    assert (row.status, row.attempts) == ("failed", 2)


async def test_unknown_kind_fails_without_retry(container: ApplicationContainer, clock: FrozenClock) -> None:
    """Неизвестный вид задачи — сразу failed."""
    await schedule(container, JobRequest("nobody.handles", "orphan", clock.now()))
    await poller(container, RecordingHandler(), clock).tick()
    assert (await job_rows(container))["orphan"].status == "failed"


async def test_expired_lease_is_reclaimed(container: ApplicationContainer, clock: FrozenClock) -> None:
    """Задача «упавшего» воркера возвращается в работу по истечении аренды."""
    await schedule(container, JobRequest("test.remind", "stuck", clock.now()))
    async with container.session_factory() as session, session.begin():
        await session.execute(
            update(jobs).values(status="running", locked_until=clock.now() - timedelta(seconds=1), attempts=1)
        )
    handler = RecordingHandler()
    assert await poller(container, handler, clock).tick() == 1
    assert len(handler.payloads) == 1
    assert (await job_rows(container))["stuck"].status == "done"
