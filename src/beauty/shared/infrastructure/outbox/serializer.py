"""Сериализация доменных событий в JSON-совместимые конверты."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from beauty.shared.domain.events import DomainEvent
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

type JsonValue = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None


class JsonValueConverter:
    """Приводит значения полей события к JSON-типам.

    Конвертеры выбираются по типу значения (Strategy): порядок важен, потому что
    ``bool`` — подкласс ``int``, а ``datetime`` — подкласс ``date``. Неизвестный тип —
    ошибка: лучше упасть при записи в outbox, чем опубликовать нечитаемое событие.
    """

    def __init__(self) -> None:
        """Зарегистрировать конвертеры."""
        self._converters: tuple[tuple[type[Any], Callable[[Any], JsonValue]], ...] = (
            (bool, lambda value: value),
            (int, lambda value: value),
            (float, lambda value: value),
            (str, lambda value: value),
            (UUID, str),
            (datetime, lambda value: value.isoformat()),
            (date, lambda value: value.isoformat()),
            (timedelta, lambda value: value.total_seconds()),
            (Decimal, str),
            (Enum, lambda value: self.convert(value.value)),
        )

    def convert(self, value: Any) -> JsonValue:
        """Преобразовать значение рекурсивно."""
        if value is None:
            return None
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {item.name: self.convert(getattr(value, item.name)) for item in dataclasses.fields(value)}
        if isinstance(value, Mapping):
            return {str(key): self.convert(item) for key, item in value.items()}
        if isinstance(value, list | tuple | frozenset | set):
            return [self.convert(item) for item in value]
        for value_type, converter in self._converters:
            if isinstance(value, value_type):
                return converter(value)
        raise TypeError(f"Тип {type(value).__name__} нельзя сериализовать в событие")


class EventSerializer:
    """Превращает доменное событие в ``EventEnvelope``."""

    _ENVELOPE_FIELDS = frozenset({"event_id", "occurred_at"})

    def __init__(self, converter: JsonValueConverter | None = None) -> None:
        """Использовать переданный конвертер значений или стандартный."""
        self._converter = converter or JsonValueConverter()

    def to_envelope(self, event: DomainEvent) -> EventEnvelope:
        """Сериализовать событие."""
        payload: dict[str, Any] = {
            item.name: self._converter.convert(getattr(event, item.name))
            for item in dataclasses.fields(event)
            if item.name not in self._ENVELOPE_FIELDS
        }
        return EventEnvelope(
            message_id=event.event_id,
            routing_key=event.routing_key,
            event_type=type(event).__name__,
            event_version=event.version,
            occurred_at=event.occurred_at,
            payload=payload,
        )
