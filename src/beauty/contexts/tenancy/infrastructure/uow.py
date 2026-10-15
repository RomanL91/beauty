"""Unit of Work Tenancy на SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.infrastructure.repositories import SqlAlchemyMasterRepository
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyTenancyUnitOfWork(SqlAlchemyUnitOfWork, TenancyUnitOfWork):
    """Создаёт репозиторий мастеров поверх сессии текущей единицы работы."""

    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Инициализировать репозитории."""
        self.masters = SqlAlchemyMasterRepository(session, tracker)
