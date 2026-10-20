"""Unit of Work Clientbook на SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from beauty.contexts.clientbook.application.uow import ClientbookUnitOfWork
from beauty.contexts.clientbook.infrastructure.repositories import SqlAlchemyClientFileRepository
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyClientbookUnitOfWork(SqlAlchemyUnitOfWork, ClientbookUnitOfWork):
    """Карточки клиентов поверх сессии единицы работы."""

    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Инициализировать репозитории."""
        self.files = SqlAlchemyClientFileRepository(session, tracker)
