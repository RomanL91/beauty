"""Императивный маппинг подписок."""

from __future__ import annotations

from typing import ClassVar

from beauty.contexts.notifications.domain.subscription import PushSubscription
from beauty.contexts.notifications.infrastructure.tables import push_subscriptions
from beauty.shared.infrastructure.db.metadata import mapper_registry


class NotificationsOrmMapper:
    """Подписка — с оптимистичной блокировкой."""

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(
            PushSubscription, push_subscriptions, version_id_col=push_subscriptions.c.version
        )
        cls._mapped = True
