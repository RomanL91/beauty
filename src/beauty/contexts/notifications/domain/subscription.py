"""Агрегат ``PushSubscription`` — устройство, подписанное на уведомления.

Подписка принадлежит учётной записи и приложению: клиентское PWA — на странице конкретного
мастера (у каждого поддомена свой service worker и свой ``endpoint``), PWA мастера — его
кабинету. ``endpoint`` уникален: повторная подписка того же устройства обновляет ключи и
владельца (на устройстве мог войти другой человек).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from beauty.contexts.notifications.domain.errors import InvalidSubscription
from beauty.shared.domain.aggregate import AggregateRoot

MAX_ENDPOINT = 2048
MAX_KEY = 256


class PushApp(StrEnum):
    """Какое приложение подписалось."""

    CLIENT = "client"
    MASTER = "master"


class PushSubscription(AggregateRoot):
    """Подписка устройства."""

    def __init__(
        self,
        subscription_id: UUID,
        account_id: UUID,
        app: PushApp,
        master_id: UUID,
        endpoint: str,
        p256dh: str,
        auth: str,
        expires_at: datetime | None,
        now: datetime,
    ) -> None:
        """Создать подписку (используйте ``create``)."""
        self.id = subscription_id
        self.account_id = account_id
        self.app = app
        self.master_id = master_id
        self.endpoint = endpoint
        self.p256dh = p256dh
        self.auth = auth
        self.expires_at = expires_at
        self.created_at = now
        self.updated_at = now

    @classmethod
    def create(
        cls,
        *,
        subscription_id: UUID,
        account_id: UUID,
        app: PushApp,
        master_id: UUID,
        endpoint: str,
        p256dh: str,
        auth: str,
        expires_at: datetime | None,
        now: datetime,
    ) -> PushSubscription:
        """Подписать устройство (endpoint — https, ключи — непустые)."""
        _validate(endpoint, p256dh, auth)
        return cls(subscription_id, account_id, app, master_id, endpoint, p256dh, auth, expires_at, now)

    def renew(
        self,
        *,
        account_id: UUID,
        app: PushApp,
        master_id: UUID,
        p256dh: str,
        auth: str,
        expires_at: datetime | None,
        now: datetime,
    ) -> None:
        """То же устройство подписалось снова: новые ключи, владелец, приложение."""
        _validate(self.endpoint, p256dh, auth)
        self.account_id = account_id
        self.app = app
        self.master_id = master_id
        self.p256dh = p256dh
        self.auth = auth
        self.expires_at = expires_at
        self.updated_at = now


def _validate(endpoint: str, p256dh: str, auth: str) -> None:
    if not endpoint.startswith("https://") or len(endpoint) > MAX_ENDPOINT:
        raise InvalidSubscription("endpoint — https-адрес push-сервиса")
    if not (0 < len(p256dh) <= MAX_KEY and 0 < len(auth) <= MAX_KEY):
        raise InvalidSubscription("Нужны ключи p256dh и auth")
