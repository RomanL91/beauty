"""Политика обработки сбоев консьюмера: повтор с задержкой или DLQ."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage

from beauty.shared.infrastructure.messaging.codec import (
    HEADER_ATTEMPT,
    HEADER_LAST_ERROR,
    HEADER_ROUTING_KEY,
    EnvelopeCodec,
)
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

logger = logging.getLogger(__name__)

_MAX_ERROR_HEADER = 500


class FailureDecision(ABC):
    """Решение о судьбе сообщения после ошибки (Strategy)."""

    @abstractmethod
    def target_queue(self, spec: ConsumerQueueSpec) -> str:
        """Очередь, куда переложить сообщение."""


class RetryLater(FailureDecision):
    """Отложить сообщение в retry-очередь попытки ``attempt``."""

    def __init__(self, attempt: int) -> None:
        """Запомнить номер попытки."""
        self.attempt = attempt

    def target_queue(self, spec: ConsumerQueueSpec) -> str:
        """Retry-очередь с нужной задержкой."""
        return spec.retry_queue_name(self.attempt)


class DeadLetter(FailureDecision):
    """Отправить сообщение в DLQ."""

    def target_queue(self, spec: ConsumerQueueSpec) -> str:
        """DLQ консьюмера."""
        return spec.dead_letter_queue_name


class RetryFailurePolicy:
    """Выбирает решение по номеру попытки и перекладывает сообщение.

    Порядок «опубликовать копию → ack оригинала» гарантирует, что сообщение не
    потеряется: при падении между шагами оригинал вернётся в очередь, а возможный
    дубликат отсечёт inbox.
    """

    def __init__(self, spec: ConsumerQueueSpec, codec: EnvelopeCodec) -> None:
        """Связать политику с очередью консьюмера."""
        self._spec = spec
        self._codec = codec

    def decide(self, attempt: int, retryable: bool) -> FailureDecision:
        """Выбрать стратегию: повтор, пока не исчерпаны задержки, иначе DLQ."""
        if retryable and attempt < len(self._spec.retry.delays):
            return RetryLater(attempt)
        return DeadLetter()

    async def handle_failure(
        self,
        default_exchange: AbstractExchange,
        message: AbstractIncomingMessage,
        envelope: EventEnvelope | None,
        error: Exception,
        retryable: bool = True,
    ) -> None:
        """Переложить сообщение согласно решению и подтвердить оригинал."""
        attempt = envelope.attempt if envelope is not None else 0
        decision = self.decide(attempt, retryable)
        target = decision.target_queue(self._spec)
        headers: dict[str, Any] = dict(message.headers or {})
        headers[HEADER_ATTEMPT] = attempt + 1
        headers[HEADER_LAST_ERROR] = f"{type(error).__name__}: {error}"[:_MAX_ERROR_HEADER]
        headers.setdefault(HEADER_ROUTING_KEY, message.routing_key or "")
        if envelope is not None:
            outgoing = self._codec.encode(envelope, extra_headers=headers)
        else:
            outgoing = self._copy_raw(message, headers)
        await default_exchange.publish(outgoing, routing_key=target)
        await message.ack()
        logger.warning("Сообщение %s → %s после ошибки: %s", message.message_id, target, error)

    @staticmethod
    def _copy_raw(message: AbstractIncomingMessage, headers: dict[str, Any]) -> aio_pika.Message:
        """Скопировать нераспознанное сообщение как есть (для DLQ)."""
        return aio_pika.Message(
            body=message.body,
            content_type=message.content_type,
            message_id=message.message_id,
            type=message.type,
            headers=headers,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
