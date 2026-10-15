"""Трекер агрегатов, прошедших через репозитории в рамках Unit of Work."""

from __future__ import annotations

from beauty.shared.domain.aggregate import AggregateRoot
from beauty.shared.domain.events import DomainEvent


class AggregateTracker:
    """Запоминает агрегаты, чтобы при коммите собрать их доменные события.

    Репозиторий регистрирует каждый агрегат, который вернул или принял. События
    собираются в порядке первого появления агрегата и порядке записи внутри него —
    так outbox сохраняет причинно-следственный порядок фактов.
    """

    def __init__(self) -> None:
        """Создать пустой трекер."""
        self._seen: dict[int, AggregateRoot] = {}

    def track[A: AggregateRoot](self, aggregate: A) -> A:
        """Зарегистрировать агрегат и вернуть его же (удобно в цепочках)."""
        self._seen.setdefault(id(aggregate), aggregate)
        return aggregate

    def collect_events(self) -> list[DomainEvent]:
        """Забрать события всех отслеживаемых агрегатов."""
        events: list[DomainEvent] = []
        for aggregate in self._seen.values():
            events.extend(aggregate.pull_events())
        return events
