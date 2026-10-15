"""Доменные события.

Событие — неизменяемый факт, который уже произошёл. Агрегат записывает события в
процессе выполнения команды, Unit of Work при коммите сохраняет их в outbox в той же
транзакции, а relay публикует их в RabbitMQ. Ключ маршрутизации задаётся на классе
события и имеет вид ``<контекст>.<агрегат>.<событие>``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from beauty.shared.domain.ids import default_id_generator


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Базовый класс доменного события.

    Атрибуты:
        event_id: уникальный id события; в брокере он же ``message_id``, по нему
            консьюмеры обеспечивают идемпотентность (inbox).
        occurred_at: момент, когда факт произошёл (из ``Clock``).
    """

    routing_key: ClassVar[str] = "shared.event.unspecified"
    version: ClassVar[int] = 1

    occurred_at: datetime
    event_id: UUID = field(default_factory=default_id_generator.new)
