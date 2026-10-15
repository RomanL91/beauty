"""Декларативное описание топологии RabbitMQ."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Задержки повторов; число попыток = ``len(delays) + 1``."""

    delays: tuple[timedelta, ...] = (timedelta(seconds=5), timedelta(seconds=30), timedelta(minutes=5))

    @property
    def max_attempts(self) -> int:
        """Общее число попыток обработки."""
        return len(self.delays) + 1


@dataclass(frozen=True, slots=True)
class ConsumerQueueSpec:
    """Очередь консьюмера и её инфраструктура повторов.

    Атрибуты:
        name: логическое имя консьюмера (очередь — ``q.<name>``).
        binding_keys: шаблоны ключей маршрутизации (``identity.client.*``).
        retry: политика повторов.
        single_active_consumer: только один активный потребитель — строгий порядок.
        transient: эксклюзивная auto-delete очередь экземпляра процесса (realtime-мост);
            повторов и DLQ у неё нет.
    """

    name: str
    binding_keys: tuple[str, ...]
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    single_active_consumer: bool = False
    transient: bool = False

    @property
    def queue_name(self) -> str:
        """Имя основной очереди."""
        return f"q.{self.name}"

    def retry_queue_name(self, attempt: int) -> str:
        """Имя retry-очереди для попытки с номером ``attempt`` (с нуля)."""
        return f"{self.queue_name}.retry.{attempt}"

    @property
    def dead_letter_queue_name(self) -> str:
        """Имя очереди «мёртвых» сообщений."""
        return f"{self.queue_name}.dlq"


class TopologyDeclarer:
    """Идемпотентно объявляет exchange, очереди и привязки."""

    def __init__(self, events_exchange: str) -> None:
        """Запомнить имя exchange доменных событий."""
        self._events_exchange = events_exchange

    async def declare_exchange(self, channel: AbstractChannel) -> AbstractExchange:
        """Объявить topic-exchange событий."""
        return await channel.declare_exchange(
            self._events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )

    async def declare_consumer(self, channel: AbstractChannel, spec: ConsumerQueueSpec) -> AbstractQueue:
        """Объявить очередь консьюмера со всей обвязкой и вернуть основную очередь."""
        exchange = await self.declare_exchange(channel)
        if spec.transient:
            queue = await channel.declare_queue(exclusive=True, auto_delete=True)
        else:
            queue = await channel.declare_queue(
                spec.queue_name, durable=True, arguments=self._main_arguments(spec)
            )
            await self._declare_retry_queues(channel, spec)
            await channel.declare_queue(
                spec.dead_letter_queue_name, durable=True, arguments={"x-queue-type": "quorum"}
            )
        for key in spec.binding_keys:
            await queue.bind(exchange, routing_key=key)
        return queue

    @staticmethod
    def _main_arguments(spec: ConsumerQueueSpec) -> dict[str, Any]:
        """Аргументы основной quorum-очереди."""
        arguments: dict[str, Any] = {"x-queue-type": "quorum"}
        if spec.single_active_consumer:
            arguments["x-single-active-consumer"] = True
        return arguments

    @staticmethod
    async def _declare_retry_queues(channel: AbstractChannel, spec: ConsumerQueueSpec) -> None:
        """Объявить retry-очереди: по истечении TTL сообщение уходит обратно в основную."""
        for attempt, delay in enumerate(spec.retry.delays):
            await channel.declare_queue(
                spec.retry_queue_name(attempt),
                durable=True,
                arguments={
                    "x-queue-type": "quorum",
                    "x-message-ttl": int(delay.total_seconds() * 1000),
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": spec.queue_name,
                    "x-dead-letter-strategy": "at-least-once",
                    "x-overflow": "reject-publish",
                },
            )
