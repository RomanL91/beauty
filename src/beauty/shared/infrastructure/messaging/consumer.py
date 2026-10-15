"""Консьюмер очереди RabbitMQ."""

from __future__ import annotations

import asyncio
import logging

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractQueue

from beauty.shared.infrastructure.messaging.codec import EnvelopeCodec, MalformedMessageError
from beauty.shared.infrastructure.messaging.connection import RabbitConnection
from beauty.shared.infrastructure.messaging.failure import RetryFailurePolicy
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec, TopologyDeclarer
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

logger = logging.getLogger(__name__)


class RabbitConsumer:
    """Потребляет очередь консьюмера и вызывает обработчик.

    Конкурентность ограничена ``prefetch``: aio-pika запускает колбэк на каждое
    сообщение отдельной задачей, а брокер не отдаст больше ``prefetch``
    неподтверждённых сообщений. Ack — только после успешной обработки (и коммита в
    обработчике). При остановке консьюмер перестаёт брать новые сообщения и
    дожидается обработки уже взятых.
    """

    def __init__(
        self,
        connection: RabbitConnection,
        topology: TopologyDeclarer,
        spec: ConsumerQueueSpec,
        handler: IntegrationEventHandler,
        codec: EnvelopeCodec,
        prefetch: int = 32,
    ) -> None:
        """Собрать консьюмер."""
        self._connection = connection
        self._topology = topology
        self._spec = spec
        self._handler = handler
        self._codec = codec
        self._prefetch = prefetch
        self._failure = RetryFailurePolicy(spec, codec)
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None
        self._consumer_tag: str | None = None
        self._in_flight = 0
        self._drained = asyncio.Event()
        self._drained.set()

    async def start(self) -> None:
        """Объявить топологию и начать потребление."""
        self._channel = await self._connection.channel(prefetch=self._prefetch)
        self._queue = await self._topology.declare_consumer(self._channel, self._spec)
        self._consumer_tag = await self._queue.consume(self._on_message)
        logger.info("Консьюмер %s запущен", self._spec.name)

    async def stop(self, timeout: float = 30.0) -> None:
        """Прекратить потребление и дождаться сообщений в обработке."""
        if self._queue is not None and self._consumer_tag is not None:
            await self._queue.cancel(self._consumer_tag)
            self._consumer_tag = None
        try:
            await asyncio.wait_for(self._drained.wait(), timeout)
        except TimeoutError:
            logger.warning(
                "Консьюмер %s: %s сообщений не успели обработаться", self._spec.name, self._in_flight
            )
        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        """Обработать одно сообщение."""
        self._in_flight += 1
        self._drained.clear()
        try:
            await self._process(message)
        finally:
            self._in_flight -= 1
            if self._in_flight == 0:
                self._drained.set()

    async def _process(self, message: AbstractIncomingMessage) -> None:
        """Декодировать, обработать, подтвердить или переложить."""
        channel = self._channel
        if channel is None:  # pragma: no cover - защита от гонки остановки
            await message.nack(requeue=True)
            return
        try:
            envelope = self._codec.decode(message)
        except MalformedMessageError as error:
            await self._fail(channel, message, None, error, retryable=False)
            return
        try:
            await self._handler.handle(envelope)
        except Exception as error:
            await self._fail(channel, message, envelope, error, retryable=True)
            return
        await message.ack()

    async def _fail(
        self,
        channel: AbstractChannel,
        message: AbstractIncomingMessage,
        envelope: EventEnvelope | None,
        error: Exception,
        retryable: bool,
    ) -> None:
        """Применить политику сбоев (для transient-очередей — просто отбросить)."""
        if self._spec.transient:
            logger.warning("Realtime-сообщение %s отброшено: %s", message.message_id, error)
            await message.ack()
            return
        await self._failure.handle_failure(
            channel.default_exchange, message, envelope, error, retryable=retryable
        )
