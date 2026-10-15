"""Базовые классы сущности и корня агрегата.

Агрегаты маппятся на таблицы императивно (classical mapping), поэтому SQLAlchemy
создаёт загруженные из БД объекты в обход ``__init__``. Список несохранённых событий
инициализируется лениво — так он есть и у созданных, и у загруженных агрегатов.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from beauty.shared.domain.events import DomainEvent


class Entity:
    """Сущность: объект с идентичностью, равенство определяется по ``id``."""

    id: UUID

    def __eq__(self, other: object) -> bool:
        """Сравнить сущности по типу и идентификатору."""
        if not isinstance(other, Entity):
            return NotImplemented
        return type(self) is type(other) and self.id == other.id

    def __hash__(self) -> int:
        """Хеш по типу и идентификатору."""
        return hash((type(self), self.id))


class AggregateRoot(Entity):
    """Корень агрегата — граница транзакционной согласованности.

    Атрибуты:
        version: номер версии для оптимистичной блокировки; маппер увеличивает его
            при каждом UPDATE и проверяет в WHERE.
    """

    version: int

    @property
    def _pending_events(self) -> list[DomainEvent]:
        """Ленивый список событий, ещё не забранных Unit of Work."""
        state: dict[str, Any] = self.__dict__
        events: list[DomainEvent] = state.setdefault("_domain_events", [])
        return events

    def _record(self, event: DomainEvent) -> None:
        """Зафиксировать событие агрегата."""
        self._pending_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Забрать накопленные события и очистить буфер."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    @property
    def has_pending_events(self) -> bool:
        """Есть ли события, ожидающие сохранения в outbox."""
        return bool(self._pending_events)
