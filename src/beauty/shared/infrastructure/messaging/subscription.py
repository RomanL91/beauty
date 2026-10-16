"""Подписка контекста на интеграционные события."""

from __future__ import annotations

from dataclasses import dataclass

from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec


@dataclass(frozen=True, slots=True)
class EventSubscription:
    """Очередь консьюмера и обработчик (без inbox — его добавляет процесс-воркер)."""

    spec: ConsumerQueueSpec
    handler: IntegrationEventHandler
