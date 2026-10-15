"""Конверт интеграционного события — формат, в котором событие путешествует по брокеру."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Сериализованное событие с метаданными.

    Атрибуты:
        message_id: id события; ключ идемпотентности для inbox.
        routing_key: ключ маршрутизации ``<контекст>.<агрегат>.<событие>``.
        event_type: имя класса события (для логов и отладки).
        event_version: версия схемы полезной нагрузки.
        occurred_at: момент факта.
        payload: JSON-совместимое тело события.
        attempt: номер попытки обработки (растёт при повторах через retry-очереди).
    """

    message_id: UUID
    routing_key: str
    event_type: str
    event_version: int
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    attempt: int = 0

    def body(self) -> bytes:
        """Тело AMQP-сообщения: только полезная нагрузка в UTF-8 JSON."""
        return json.dumps(self.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
