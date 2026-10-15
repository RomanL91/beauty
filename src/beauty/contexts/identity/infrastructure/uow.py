"""Unit of Work Identity на SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.contexts.identity.infrastructure.repositories import (
    SqlAlchemyAuthChallengeRepository,
    SqlAlchemyClientAccountRepository,
    SqlAlchemyClientSessionRepository,
)
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyIdentityUnitOfWork(SqlAlchemyUnitOfWork, IdentityUnitOfWork):
    """Создаёт репозитории Identity поверх сессии текущей единицы работы."""

    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Инициализировать репозитории."""
        self.challenges = SqlAlchemyAuthChallengeRepository(session, tracker)
        self.accounts = SqlAlchemyClientAccountRepository(session, tracker)
        self.sessions = SqlAlchemyClientSessionRepository(session, tracker)
