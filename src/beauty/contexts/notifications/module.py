"""Модуль контекста Notifications."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.notifications.application.notify import NotifyAbout, NotifyAboutHandler
from beauty.contexts.notifications.application.ports import Directory, PushSender
from beauty.contexts.notifications.application.subscriptions import (
    Subscribe,
    SubscribeHandler,
    Unsubscribe,
    UnsubscribeHandler,
)
from beauty.contexts.notifications.infrastructure.mapping import NotificationsOrmMapper
from beauty.contexts.notifications.infrastructure.uow import SqlAlchemyNotificationsUnitOfWork
from beauty.contexts.notifications.presentation.api import push_router
from beauty.contexts.notifications.presentation.consumers import BINDING_KEYS, PushConsumer
from beauty.shared.application.mediator import Mediator
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.messaging.subscription import EventSubscription
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.web.auth import BearerAuth, MasterAuth
from beauty.shared.infrastructure.web.errors import HttpErrorMapper

_HTTP_STATUSES: dict[str, int] = {
    "invalid_push_subscription": 422,
    "unknown_master_page": 422,
    "push_subscription_not_found": 404,
}


@dataclass(frozen=True, slots=True)
class NotificationsDependencies:
    """Общие зависимости, отправитель и справочник соседей."""

    session_factory: async_sessionmaker[AsyncSession]
    outbox_writer: OutboxWriter
    clock: Clock
    ids: IdGenerator
    sender: PushSender
    directory: Directory


class NotificationsModule:
    """Сборка контекста Notifications."""

    def __init__(self, dependencies: NotificationsDependencies) -> None:
        """Создать долгоживущие компоненты."""
        NotificationsOrmMapper.map()
        self._deps = dependencies

    def register(self, mediator: Mediator, http_errors: HttpErrorMapper) -> None:
        """Зарегистрировать обработчики и коды ошибок."""
        deps = self._deps
        mediator.register(
            Subscribe, lambda: SubscribeHandler(self._uow(), deps.directory, deps.clock, deps.ids)
        )
        mediator.register(Unsubscribe, lambda: UnsubscribeHandler(self._uow()))
        mediator.register(NotifyAbout, lambda: self.notify_handler(deps.sender))
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def notify_handler(self, sender: PushSender) -> NotifyAboutHandler:
        """Обработчик уведомлений с этим отправителем (в тестах — записывающим)."""
        return NotifyAboutHandler(self._uow, self._deps.directory, sender, self._deps.clock)

    def subscriptions(self, mediator: Mediator) -> tuple[EventSubscription, ...]:
        """Консьюмер уведомлений: отправка — внешний вызов, без общей транзакции."""
        return (
            EventSubscription(
                ConsumerQueueSpec(name="notifications.push", binding_keys=BINDING_KEYS),
                PushConsumer(mediator),
                ambient_transaction=False,
            ),
        )

    def api_router(self, mediator: Mediator, bearer: BearerAuth, master_auth: MasterAuth) -> APIRouter:
        """``/push/subscriptions``."""
        return push_router(mediator, bearer, master_auth)

    def _uow(self) -> SqlAlchemyNotificationsUnitOfWork:
        """Новый Unit of Work."""
        return SqlAlchemyNotificationsUnitOfWork(self._deps.session_factory, self._deps.outbox_writer)
