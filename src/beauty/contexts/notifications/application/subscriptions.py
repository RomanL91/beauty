"""Подписка устройства на уведомления и отписка."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.contexts.notifications.application.errors import (
    PushSubscriptionNotFoundError,
    UnknownMasterPageError,
)
from beauty.contexts.notifications.application.ports import Directory
from beauty.contexts.notifications.application.uow import NotificationsUnitOfWork
from beauty.contexts.notifications.domain.subscription import PushApp, PushSubscription
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class Subscribe(Command[UUID]):
    """Подписать устройство.

    ``master_id`` — для приложения мастера (кабинет учётной записи); для клиентского —
    ``master_slug`` страницы, на которой подписались.
    """

    account_id: UUID
    app: PushApp
    endpoint: str
    p256dh: str
    auth: str
    expires_at: datetime | None = None
    master_id: UUID | None = None
    master_slug: str | None = None


class SubscribeHandler(Handler[Subscribe, UUID]):
    """Идемпотентно по ``endpoint``: то же устройство — та же подписка."""

    def __init__(
        self, uow: NotificationsUnitOfWork, directory: Directory, clock: Clock, ids: IdGenerator
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._directory = directory
        self._clock = clock
        self._ids = ids

    async def handle(self, message: Subscribe) -> UUID:
        """Сохранить подписку."""
        master_id = message.master_id
        if message.app is PushApp.CLIENT:
            slug = (message.master_slug or "").strip()
            master_id = await self._directory.master_by_slug(slug) if slug else None
        if master_id is None:
            raise UnknownMasterPageError()
        now = self._clock.now()
        async with self._uow as uow:
            existing = await uow.subscriptions.by_endpoint(message.endpoint)
            if existing is None:
                subscription = PushSubscription.create(
                    subscription_id=self._ids.new(),
                    account_id=message.account_id,
                    app=message.app,
                    master_id=master_id,
                    endpoint=message.endpoint,
                    p256dh=message.p256dh,
                    auth=message.auth,
                    expires_at=message.expires_at,
                    now=now,
                )
                uow.subscriptions.add(subscription)
            else:
                existing.renew(
                    account_id=message.account_id,
                    app=message.app,
                    master_id=master_id,
                    p256dh=message.p256dh,
                    auth=message.auth,
                    expires_at=message.expires_at,
                    now=now,
                )
                subscription = existing
            await uow.commit()
            return subscription.id


@dataclass(frozen=True, slots=True)
class Unsubscribe(Command[None]):
    """Отписать своё устройство."""

    account_id: UUID
    subscription_id: UUID


class UnsubscribeHandler(Handler[Unsubscribe, None]):
    """Чужая подписка неотличима от несуществующей."""

    def __init__(self, uow: NotificationsUnitOfWork) -> None:
        """Получить Unit of Work."""
        self._uow = uow

    async def handle(self, message: Unsubscribe) -> None:
        """Удалить."""
        async with self._uow as uow:
            subscription = await uow.subscriptions.get(message.subscription_id)
            if subscription is None or subscription.account_id != message.account_id:
                raise PushSubscriptionNotFoundError()
            await uow.subscriptions.remove(subscription)
            await uow.commit()
