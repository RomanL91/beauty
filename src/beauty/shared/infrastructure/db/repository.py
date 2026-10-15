"""Базовый репозиторий на SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from beauty.shared.domain.aggregate import AggregateRoot
from beauty.shared.infrastructure.db.tracker import AggregateTracker


class SqlAlchemyRepository[A: AggregateRoot]:
    """Репозиторий агрегата: коллекция в памяти поверх сессии.

    Репозиторий не коммитит и не флашит — это ответственность Unit of Work. Каждый
    выданный или добавленный агрегат регистрируется в трекере, чтобы его события
    попали в outbox.
    """

    def __init__(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Связать репозиторий с сессией и трекером текущего Unit of Work."""
        self._session = session
        self._tracker = tracker

    def add(self, aggregate: A) -> None:
        """Добавить новый агрегат."""
        self._session.add(aggregate)
        self._tracker.track(aggregate)

    def _seen(self, aggregate: A | None) -> A | None:
        """Зарегистрировать загруженный агрегат в трекере (``None`` пропускается)."""
        return None if aggregate is None else self._tracker.track(aggregate)
