"""Публикация событий в RabbitMQ."""

from __future__ import annotations

import asyncio

from aio_pika.abc import AbstractChannel, AbstractExchange

from beauty.shared.infrastructure.messaging.codec import EnvelopeCodec
from beauty.shared.infrastructure.messaging.connection import RabbitConnection
from beauty.shared.infrastructure.messaging.topology import TopologyDeclarer
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.outbox.relay import EventPublisher


class RabbitEventPublisher(EventPublisher):
    """Публикует конверты в topic-exchange с publisher confirms.

    ``await exchange.publish`` завершается только после ``basic.ack`` брокера: relay
    помечает запись outbox опубликованной лишь после подтверждения. Канал
    создаётся лениво под замком, чтобы параллельные первые вызовы не открыли два.
    """

    def __init__(
        self, connection: RabbitConnection, topology: TopologyDeclarer, codec: EnvelopeCodec
    ) -> None:
        """Собрать publisher."""
        self._connection = connection
        self._topology = topology
        self._codec = codec
        self._lock = asyncio.Lock()
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def publish(self, envelope: EventEnvelope) -> None:
        """Опубликовать конверт и дождаться подтверждения."""
        exchange = await self._ensure_exchange()
        await exchange.publish(self._codec.encode(envelope), routing_key=envelope.routing_key)

    async def _ensure_exchange(self) -> AbstractExchange:
        """Открыть канал и объявить exchange при первом обращении."""
        if self._exchange is not None and self._channel is not None and not self._channel.is_closed:
            return self._exchange
        async with self._lock:
            if self._exchange is None or self._channel is None or self._channel.is_closed:
                self._channel = await self._connection.channel(publisher_confirms=True)
                self._exchange = await self._topology.declare_exchange(self._channel)
            return self._exchange
