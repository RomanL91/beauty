"""Порты репозиториев Notifications."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from beauty.contexts.notifications.domain.subscription import PushApp, PushSubscription


class PushSubscriptionRepository(ABC):
    """Подписки устройств."""

    @abstractmethod
    def add(self, subscription: PushSubscription) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, subscription_id: UUID) -> PushSubscription | None:
        """По id."""

    @abstractmethod
    async def by_endpoint(self, endpoint: str) -> PushSubscription | None:
        """По адресу push-сервиса (уникален)."""

    @abstractmethod
    async def audience(
        self, app: PushApp, master_id: UUID, account_id: UUID | None = None
    ) -> list[PushSubscription]:
        """Устройства приложения мастера (клиентского — только этой учётной записи)."""

    @abstractmethod
    async def remove(self, subscription: PushSubscription) -> None:
        """Удалить."""
