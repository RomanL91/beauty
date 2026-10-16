"""Уведомить адресатов о событии соседнего контекста."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.notifications.application.ports import Directory, PushSender, PushTarget, SendOutcome
from beauty.contexts.notifications.application.texts import (
    Notification,
    appointment_notifications,
    message_notifications,
    office_notifications,
)
from beauty.contexts.notifications.application.uow import NotificationsUnitOfWork
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock

logger = logging.getLogger(__name__)

APPOINTMENTS = "booking.appointment."
MESSAGES = "conversations.message.added"
OFFICE = "agent.office.feed_changed"


@dataclass(frozen=True, slots=True)
class NotifyAbout(Command[int]):
    """Событие соседнего контекста (ключ и данные) → уведомления; вернуть число отправленных."""

    routing_key: str
    payload: Mapping[str, Any]


class NotifyAboutHandler(Handler[NotifyAbout, int]):
    """Тексты — по событию, адресаты — подписки; исчезнувшие подписки удаляются."""

    def __init__(
        self,
        uow_factory: Callable[[], NotificationsUnitOfWork],
        directory: Directory,
        sender: PushSender,
        clock: Clock,
    ) -> None:
        """Получить зависимости (чтение подписок и удаление исчезнувших — разные транзакции)."""
        self._uow_factory = uow_factory
        self._directory = directory
        self._sender = sender
        self._clock = clock

    async def handle(self, message: NotifyAbout) -> int:
        """Отправить."""
        sent = 0
        for notification in await self._compose(message.routing_key, message.payload):
            sent += await self._deliver(notification)
        return sent

    async def _compose(self, routing_key: str, payload: Mapping[str, Any]) -> list[Notification]:
        if routing_key == OFFICE:
            return office_notifications(payload)
        if not (routing_key.startswith(APPOINTMENTS) or routing_key == MESSAGES):
            return []
        master_id = UUID(str(payload["master_id"]))
        master = await self._directory.master(master_id)
        if master is None:
            return []
        if routing_key == MESSAGES:
            client = None
            if payload.get("author") == "client":
                client = await self._directory.client_name(master_id, UUID(str(payload["conversation_id"])))
            return message_notifications(payload, master.name, client)
        today = self._clock.now().astimezone(ZoneInfo(master.timezone)).date()
        return appointment_notifications(routing_key.removeprefix(APPOINTMENTS), payload, master.name, today)

    async def _deliver(self, notification: Notification) -> int:
        audience = notification.audience
        async with self._uow_factory() as uow:
            targets = [
                (s.id, PushTarget(s.endpoint, s.p256dh, s.auth))
                for s in await uow.subscriptions.audience(
                    audience.app, audience.master_id, audience.account_id
                )
            ]
        sent = 0
        for subscription_id, target in targets:
            outcome = await self._sender.send(target, notification.payload)
            if outcome is SendOutcome.SENT:
                sent += 1
            elif outcome is SendOutcome.GONE:
                await self._forget(subscription_id)
        return sent

    async def _forget(self, subscription_id: UUID) -> None:
        async with self._uow_factory() as uow:
            subscription = await uow.subscriptions.get(subscription_id)
            if subscription is not None:
                await uow.subscriptions.remove(subscription)
                await uow.commit()
                logger.info("Подписка %s исчезла у push-сервиса — удалена", subscription_id)
