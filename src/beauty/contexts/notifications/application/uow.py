"""Unit of Work контекста Notifications."""

from __future__ import annotations

from beauty.contexts.notifications.domain.repositories import PushSubscriptionRepository
from beauty.shared.application.uow import UnitOfWork


class NotificationsUnitOfWork(UnitOfWork):
    """Подписки устройств."""

    subscriptions: PushSubscriptionRepository
