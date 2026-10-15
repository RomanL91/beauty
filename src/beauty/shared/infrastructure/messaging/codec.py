"""Кодирование конверта в AMQP-сообщение и обратно."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

HEADER_VERSION = "x-event-version"
HEADER_OCCURRED_AT = "x-occurred-at"
HEADER_ROUTING_KEY = "x-routing-key"
HEADER_ATTEMPT = "x-attempt"
HEADER_LAST_ERROR = "x-last-error"


class MalformedMessageError(ValueError):
    """Сообщение нельзя декодировать — повтор не поможет, только DLQ."""


class EnvelopeCodec:
    """Метаданные — в свойства и заголовки AMQP, полезная нагрузка — в тело JSON.

    Исходный ключ маршрутизации дублируется в заголовок: при возврате из
    retry-очереди сообщение приходит с ключом имени очереди, а обработчику нужен
    исходный.
    """

    def encode(
        self, envelope: EventEnvelope, extra_headers: Mapping[str, Any] | None = None
    ) -> aio_pika.Message:
        """Собрать AMQP-сообщение."""
        headers: dict[str, Any] = {
            HEADER_VERSION: envelope.event_version,
            HEADER_OCCURRED_AT: envelope.occurred_at.isoformat(),
            HEADER_ROUTING_KEY: envelope.routing_key,
            HEADER_ATTEMPT: envelope.attempt,
        }
        headers.update(extra_headers or {})
        return aio_pika.Message(
            body=envelope.body(),
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=str(envelope.message_id),
            type=envelope.event_type,
            timestamp=envelope.occurred_at,
            headers=headers,
        )

    def decode(self, message: AbstractIncomingMessage) -> EventEnvelope:
        """Разобрать входящее сообщение."""
        headers = dict(message.headers or {})
        try:
            payload = json.loads(message.body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("ожидался JSON-объект")
            return EventEnvelope(
                message_id=UUID(str(message.message_id)),
                routing_key=str(headers.get(HEADER_ROUTING_KEY) or message.routing_key),
                event_type=str(message.type or ""),
                event_version=int(str(headers.get(HEADER_VERSION, 1))),
                occurred_at=datetime.fromisoformat(str(headers[HEADER_OCCURRED_AT])),
                payload=payload,
                attempt=int(str(headers.get(HEADER_ATTEMPT, 0))),
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
            raise MalformedMessageError(str(error)) from error
