"""Репозиторий подписок на SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from beauty.contexts.notifications.domain.repositories import PushSubscriptionRepository
from beauty.contexts.notifications.domain.subscription import PushApp, PushSubscription
from beauty.contexts.notifications.infrastructure.tables import push_subscriptions
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyPushSubscriptionRepository(
    SqlAlchemyRepository[PushSubscription], PushSubscriptionRepository
):
    """Подписки устройств."""

    async def get(self, subscription_id: UUID) -> PushSubscription | None:
        """По id."""
        return self._seen(await self._session.get(PushSubscription, subscription_id))

    async def by_endpoint(self, endpoint: str) -> PushSubscription | None:
        """По endpoint (уникальный индекс)."""
        statement = select(PushSubscription).where(push_subscriptions.c.endpoint == endpoint)
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())

    async def audience(
        self, app: PushApp, master_id: UUID, account_id: UUID | None = None
    ) -> list[PushSubscription]:
        """Устройства адресата."""
        statement = select(PushSubscription).where(
            push_subscriptions.c.app == app, push_subscriptions.c.master_id == master_id
        )
        if account_id is not None:
            statement = statement.where(push_subscriptions.c.account_id == account_id)
        return list((await self._session.execute(statement)).scalars())

    async def remove(self, subscription: PushSubscription) -> None:
        """Удалить."""
        await self._session.delete(subscription)
