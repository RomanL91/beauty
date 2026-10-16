"""Консьюмер Notifications: события соседних контекстов → уведомления."""

from __future__ import annotations

from beauty.contexts.notifications.application.notify import MESSAGES, OFFICE, NotifyAbout
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

BINDING_KEYS = ("booking.appointment.*", MESSAGES, OFFICE)


class PushConsumer(IntegrationEventHandler):
    """Событие → команда ``NotifyAbout``."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Уведомить адресатов."""
        await self._mediator.send(NotifyAbout(envelope.routing_key, dict(envelope.payload)))
