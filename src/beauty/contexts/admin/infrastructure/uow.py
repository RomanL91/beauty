"""Unit of Work Admin на SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from beauty.contexts.admin.application.uow import AdminUnitOfWork
from beauty.contexts.admin.infrastructure.repositories import (
    SqlAlchemyAdministratorRepository,
    SqlAlchemyAdminSessionRepository,
    SqlAlchemyAuditRepository,
)
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyAdminUnitOfWork(SqlAlchemyUnitOfWork, AdminUnitOfWork):
    """Администраторы, сессии, журнал поверх сессии единицы работы."""

    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Инициализировать репозитории."""
        self.admins = SqlAlchemyAdministratorRepository(session, tracker)
        self.sessions = SqlAlchemyAdminSessionRepository(session, tracker)
        self.audit = SqlAlchemyAuditRepository(session, tracker)
