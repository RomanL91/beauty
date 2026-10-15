"""Тесты инфраструктуры без внешних систем: сериализация, кодек, политика сбоев, хаб, SSE, хранилище."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from beauty.shared.domain.events import DomainEvent
from beauty.shared.infrastructure.messaging.codec import (
    HEADER_ATTEMPT,
    HEADER_ROUTING_KEY,
    EnvelopeCodec,
    MalformedMessageError,
)
from beauty.shared.infrastructure.messaging.failure import DeadLetter, RetryFailurePolicy, RetryLater
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec, RetryPolicy
from beauty.shared.infrastructure.outbox.serializer import EventSerializer
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.scheduling.backoff import ExponentialBackoff
from beauty.shared.infrastructure.storage.local import InvalidStorageKeyError, LocalFileStorage
from beauty.shared.infrastructure.web.sse import ServerSentEvent


class Color(StrEnum):
    RED = "red"


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str


@dataclass(frozen=True, kw_only=True)
class SomethingHappened(DomainEvent):
    routing_key = "test.something.happened"
    version = 2

    ref: UUID
    color: Color
    price: Money
    tags: tuple[str, ...]
    when: datetime


class TestEventSerializer:
    """Сериализация событий в конверт."""

    def test_converts_nested_values(self) -> None:
        """UUID, enum, вложенные VO, кортежи и даты становятся JSON-типами."""
        now = datetime(2026, 1, 1, tzinfo=UTC)
        ref = UUID(int=1)
        event = SomethingHappened(
            occurred_at=now,
            ref=ref,
            color=Color.RED,
            price=Money(Decimal("10.50"), "KZT"),
            tags=("a",),
            when=now,
        )
        envelope = EventSerializer().to_envelope(event)
        assert envelope.message_id == event.event_id
        assert envelope.routing_key == "test.something.happened"
        assert envelope.event_version == 2
        assert envelope.payload == {
            "ref": str(ref),
            "color": "red",
            "price": {"amount": "10.50", "currency": "KZT"},
            "tags": ["a"],
            "when": now.isoformat(),
        }
        json.dumps(envelope.payload)

    def test_unknown_type_rejected(self) -> None:
        """Несериализуемое значение — ошибка при записи, а не мусор в брокере."""

        @dataclass(frozen=True, kw_only=True)
        class Bad(DomainEvent):
            thing: object

        with pytest.raises(TypeError):
            EventSerializer().to_envelope(Bad(occurred_at=datetime.now(UTC), thing=object()))


@dataclass
class FakeIncoming:
    """Минимальная имитация ``AbstractIncomingMessage`` для кодека."""

    body: bytes
    headers: dict[str, Any]
    message_id: str | None
    type: str | None
    routing_key: str | None
    content_type: str | None = "application/json"


class TestEnvelopeCodec:
    """Кодек AMQP."""

    def _envelope(self) -> Any:
        event = SomethingHappened(
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            ref=UUID(int=5),
            color=Color.RED,
            price=Money(Decimal("1"), "KZT"),
            tags=(),
            when=datetime(2026, 1, 1, tzinfo=UTC),
        )
        return EventSerializer().to_envelope(event)

    def test_roundtrip_keeps_original_routing_key(self) -> None:
        """После retry-очереди ключ берётся из заголовка, а не из имени очереди."""
        codec = EnvelopeCodec()
        envelope = self._envelope()
        message = codec.encode(envelope, extra_headers={HEADER_ATTEMPT: 2})
        incoming = FakeIncoming(
            body=message.body,
            headers=dict(message.headers),
            message_id=message.message_id,
            type=message.type,
            routing_key="q.consumer",
        )
        decoded = codec.decode(incoming)  # type: ignore[arg-type]
        assert decoded.routing_key == envelope.routing_key
        assert decoded.message_id == envelope.message_id
        assert decoded.payload == envelope.payload
        assert decoded.attempt == 2

    def test_malformed_body(self) -> None:
        """Битое тело — ``MalformedMessageError``."""
        incoming = FakeIncoming(body=b"not json", headers={}, message_id="x", type=None, routing_key="k")
        with pytest.raises(MalformedMessageError):
            EnvelopeCodec().decode(incoming)  # type: ignore[arg-type]


class TestRetryFailurePolicy:
    """Решения о повторах."""

    def test_decisions_by_attempt(self) -> None:
        """Повтор по задержкам, затем DLQ; неповторяемая ошибка — сразу DLQ."""
        spec = ConsumerQueueSpec(
            name="crm.identity",
            binding_keys=("identity.#",),
            retry=RetryPolicy((timedelta(seconds=1), timedelta(seconds=10))),
        )
        policy = RetryFailurePolicy(spec, EnvelopeCodec())
        first = policy.decide(0, retryable=True)
        assert isinstance(first, RetryLater)
        assert first.target_queue(spec) == "q.crm.identity.retry.0"
        assert policy.decide(1, retryable=True).target_queue(spec) == "q.crm.identity.retry.1"
        assert isinstance(policy.decide(2, retryable=True), DeadLetter)
        assert policy.decide(0, retryable=False).target_queue(spec) == "q.crm.identity.dlq"
        assert spec.retry.max_attempts == 3

    async def test_handle_failure_publishes_then_acks(self) -> None:
        """Копия уходит в retry-очередь до ack оригинала."""
        journal: list[str] = []

        class Exchange:
            async def publish(self, message: Any, routing_key: str) -> None:
                journal.append(f"publish:{routing_key}:{message.headers[HEADER_ATTEMPT]}")

        class Incoming:
            headers = {HEADER_ROUTING_KEY: "identity.client.registered"}
            routing_key = "q.crm"
            message_id = "m-1"

            async def ack(self) -> None:
                journal.append("ack")

        spec = ConsumerQueueSpec(name="crm", binding_keys=("identity.#",))
        envelope = TestEnvelopeCodec()._envelope()
        await RetryFailurePolicy(spec, EnvelopeCodec()).handle_failure(
            Exchange(),  # type: ignore[arg-type]
            Incoming(),  # type: ignore[arg-type]
            envelope,
            RuntimeError("boom"),
        )
        assert journal == ["publish:q.crm.retry.0:1", "ack"]


class TestBackoff:
    """Экспоненциальная задержка."""

    def test_grows_and_caps(self) -> None:
        """Удвоение до потолка."""
        backoff = ExponentialBackoff(timedelta(seconds=10), timedelta(seconds=60))
        assert [backoff.delay(n).total_seconds() for n in range(1, 6)] == [10, 20, 40, 60, 60]


class TestRealtimeHub:
    """Внутрипроцессная шина."""

    async def test_delivers_to_subscribers_of_topic_only(self) -> None:
        """Сообщение получают только подписчики топика."""
        hub = RealtimeHub()
        async with hub.subscribe("a") as first, hub.subscribe("b") as second:
            assert hub.publish("a", {"n": 1}) == 1
            assert await first.next(0.1) == {"n": 1}
            assert await second.next(0.01) is None
        assert hub.publish("a", {"n": 2}) == 0

    async def test_slow_subscriber_keeps_latest(self) -> None:
        """При переполнении теряются самые старые сообщения."""
        hub = RealtimeHub(capacity=2)
        async with hub.subscribe("t") as subscription:
            for n in range(5):
                hub.publish("t", {"n": n})
            assert [await subscription.next(0.1) for _ in range(2)] == [{"n": 3}, {"n": 4}]


class TestServerSentEvent:
    """Формат SSE."""

    def test_encoding(self) -> None:
        """Поля и пустая строка-разделитель."""
        frame = ServerSentEvent(data={"status": "completed"}, event="status", retry_ms=3000).encode()
        assert frame == b'event: status\nretry: 3000\ndata: {"status":"completed"}\n\n'
        assert ServerSentEvent.heartbeat() == b": ping\n\n"


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        await asyncio.sleep(0)
        yield part


class TestLocalFileStorage:
    """Локальное хранилище файлов."""

    async def test_save_open_delete(self, tmp_path: Path) -> None:
        """Полный цикл без временных файлов на месте итогового ключа."""
        storage = LocalFileStorage(tmp_path)
        stored = await storage.save("voice", _chunks(b"abc", b"def"), "audio/ogg", ".ogg")
        assert stored.size == 6
        assert stored.key.startswith("voice/")
        assert stored.key.endswith(".ogg")
        read = b"".join([chunk async for chunk in storage.open(stored.key)])
        assert read == b"abcdef"
        assert not list(tmp_path.rglob("*.part"))
        await storage.delete(stored.key)
        await storage.delete(stored.key)

    @pytest.mark.parametrize("key", ["../etc/passwd", "voice/../../x", "/abs/path", "voice/2026/01/notauuid"])
    async def test_rejects_traversal(self, tmp_path: Path, key: str) -> None:
        """Ключи вне формата отвергаются."""
        storage = LocalFileStorage(tmp_path)
        with pytest.raises(InvalidStorageKeyError):
            await storage.delete(key)

    async def test_failed_upload_leaves_nothing(self, tmp_path: Path) -> None:
        """Оборванная загрузка не оставляет файлов."""

        async def broken() -> AsyncIterator[bytes]:
            yield b"partial"
            raise ConnectionError("клиент отключился")

        storage = LocalFileStorage(tmp_path)
        with pytest.raises(ConnectionError):
            await storage.save("voice", broken(), "audio/ogg", ".ogg")
        assert [path for path in tmp_path.rglob("*") if path.is_file()] == []
