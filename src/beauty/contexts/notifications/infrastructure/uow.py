"""Unit of Work Notifications на SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from beauty.contexts.notifications.application.uow import NotificationsUnitOfWork
from beauty.contexts.notifications.infrastructure.repositories import SqlAlchemyPushSubscriptionRepository
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyNotificationsUnitOfWork(SqlAlchemyUnitOfWork, NotificationsUnitOfWork):
    """Подписки поверх сессии единицы работы."""

    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Инициализировать репозитории."""
        self.subscriptions = SqlAlchemyPushSubscriptionRepository(session, tracker)
