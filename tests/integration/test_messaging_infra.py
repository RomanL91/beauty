"""Outbox relay, LISTEN/NOTIFY, inbox и амбиентная транзакция на реальной БД."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from beauty.bootstrap.container import ApplicationContainer
from beauty.contexts.identity.application.commands import StartTelegramAuth
from beauty.contexts.identity.infrastructure.tables import auth_challenges
from beauty.shared.domain.events import DomainEvent
from beauty.shared.infrastructure.db.scope import TransactionScope
from beauty.shared.infrastructure.inbox.guard import InboxGuard, InboxIdempotentHandler
from beauty.shared.infrastructure.inbox.table import inbox_table
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.outbox.listener import PostgresNotificationListener
from beauty.shared.infrastructure.outbox.relay import EventPublisher, OutboxRelay
from beauty.shared.infrastructure.outbox.serializer import EventSerializer
from beauty.shared.infrastructure.outbox.table import OUTBOX_NOTIFY_CHANNEL, outbox_table

pytestmark = pytest.mark.integration


@dataclass(frozen=True, kw_only=True)
class Pinged(DomainEvent):
    routing_key = "test.ping.sent"
    number: int


class RecordingPublisher(EventPublisher):
    """Публикатор, запоминающий конверты; может «упасть» на заданном номере."""

    def __init__(self, fail_on: int | None = None) -> None:
        self.published: list[EventEnvelope] = []
        self._fail_on = fail_on

    async def publish(self, envelope: EventEnvelope) -> None:
        if self._fail_on is not None and envelope.payload["number"] == self._fail_on:
            raise ConnectionError("брокер недоступен")
        await asyncio.sleep(0)
        self.published.append(envelope)


class NeverWake:
    """Источник пробуждения, который сразу возвращается."""

    async def wait(self, timeout: float) -> bool:
        return False


async def write_events(container: ApplicationContainer, count: int) -> None:
    """Записать ``count`` событий в outbox."""
    now = datetime.now(UTC)
    async with container.session_factory() as session, session.begin():
        await container.outbox_writer.write(
            session, [Pinged(occurred_at=now, number=n) for n in range(count)]
        )


def make_relay(
    container: ApplicationContainer, publisher: EventPublisher, batch_size: int = 50
) -> OutboxRelay:
    """Relay с заданным публикатором."""
    return OutboxRelay(
        container.session_factory, publisher, NeverWake(), container.clock, batch_size=batch_size
    )


async def unpublished(container: ApplicationContainer) -> int:
    """Число неопубликованных записей."""
    async with container.session_factory() as session:
        statement = (
            select(func.count()).select_from(outbox_table).where(outbox_table.c.published_at.is_(None))
        )
        return int((await session.execute(statement)).scalar_one())


async def test_relay_publishes_in_order_and_marks(container: ApplicationContainer) -> None:
    """События публикуются в порядке записи и помечаются."""
    await write_events(container, 5)
    publisher = RecordingPublisher()
    relay = make_relay(container, publisher)
    assert await relay.relay_batch() == 5
    assert [envelope.payload["number"] for envelope in publisher.published] == [0, 1, 2, 3, 4]
    assert await relay.relay_batch() == 0
    assert await unpublished(container) == 0


async def test_relay_stops_at_first_failure_and_resumes(container: ApplicationContainer) -> None:
    """Сбой посреди пачки: подтверждённые помечены, остальные ждут следующей итерации."""
    await write_events(container, 4)
    assert await make_relay(container, RecordingPublisher(fail_on=2)).relay_batch() == 2
    assert await unpublished(container) == 2
    healthy = RecordingPublisher()
    assert await make_relay(container, healthy).relay_batch() == 2
    assert [envelope.payload["number"] for envelope in healthy.published] == [2, 3]


async def test_parallel_relays_do_not_duplicate(container: ApplicationContainer) -> None:
    """Несколько relay конкурентно: SKIP LOCKED — ни одного дубля, ничего не потеряно."""
    await write_events(container, 120)
    publishers = [RecordingPublisher() for _ in range(4)]
    relays = [make_relay(container, publisher, batch_size=10) for publisher in publishers]

    async def drain(relay: OutboxRelay) -> None:
        while await relay.relay_batch():
            pass

    await asyncio.gather(*(drain(relay) for relay in relays))
    numbers = [envelope.payload["number"] for publisher in publishers for envelope in publisher.published]
    assert sorted(numbers) == list(range(120))
    assert await unpublished(container) == 0


async def test_listener_wakes_up_on_insert(container: ApplicationContainer) -> None:
    """Триггер ``pg_notify`` будит relay сразу после COMMIT."""
    listener = PostgresNotificationListener(container.settings.database.url, OUTBOX_NOTIFY_CHANNEL)
    await listener.start()
    try:
        assert await listener.wait(5.0), "слушатель не подключился"
        assert not await listener.wait(0.2)
        await write_events(container, 1)
        assert await listener.wait(5.0)
    finally:
        await listener.stop()


class StartLoginHandler(IntegrationEventHandler):
    """Обработчик, вызывающий команду через медиатор (её UoW присоединится к scope)."""

    def __init__(self, container: ApplicationContainer, fail: bool = False) -> None:
        self._container = container
        self._fail = fail

    async def handle(self, envelope: EventEnvelope) -> None:
        await self._container.mediator.send(StartTelegramAuth())
        if self._fail:
            raise RuntimeError("обработчик упал после команды")


async def count(container: ApplicationContainer, table: object) -> int:
    """Число строк в таблице."""
    async with container.session_factory() as session:
        return int((await session.execute(select(func.count()).select_from(table))).scalar_one())  # type: ignore[arg-type]


def envelope() -> EventEnvelope:
    """Конверт тестового события."""
    return EventSerializer().to_envelope(Pinged(occurred_at=datetime.now(UTC), number=1))


async def test_inbox_makes_redelivery_harmless(container: ApplicationContainer) -> None:
    """Повторная доставка того же сообщения не повторяет эффект."""
    handler = InboxIdempotentHandler(
        StartLoginHandler(container), container.transaction_scope, InboxGuard(), consumer="test"
    )
    message = envelope()
    await handler.handle(message)
    await handler.handle(message)
    assert await count(container, auth_challenges) == 1
    assert await count(container, inbox_table) == 1


async def test_inbox_mark_rolls_back_with_failed_handler(container: ApplicationContainer) -> None:
    """Если обработчик упал, не сохраняются ни эффект команды, ни отметка inbox — сообщение повторится."""
    handler = InboxIdempotentHandler(
        StartLoginHandler(container, fail=True), container.transaction_scope, InboxGuard(), consumer="test"
    )
    with pytest.raises(RuntimeError):
        await handler.handle(envelope())
    assert await count(container, auth_challenges) == 0
    assert await count(container, inbox_table) == 0


async def test_child_task_does_not_join_scope(container: ApplicationContainer) -> None:
    """Задача, порождённая внутри scope, работает в своей транзакции (AsyncSession не делится)."""
    scope: TransactionScope = container.transaction_scope
    with pytest.raises(RuntimeError):
        async with scope.begin():
            await asyncio.create_task(container.mediator.send(StartTelegramAuth()))
            await container.mediator.send(StartTelegramAuth())
            raise RuntimeError("откат scope")
    assert await count(container, auth_challenges) == 1
