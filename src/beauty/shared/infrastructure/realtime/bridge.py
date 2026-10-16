"""Мост «брокер → RealtimeHub»."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.realtime.hub import RealtimeHub


class TopicResolver(ABC):
    """Сопоставляет событию realtime-топик и сообщение для клиента (Strategy).

    Каждый контекст сам решает, какие свои события и в каком виде видны браузеру:
    наружу уходит только явно сформированное сообщение, а не весь payload.
    """

    @property
    @abstractmethod
    def binding_keys(self) -> tuple[str, ...]:
        """Ключи маршрутизации, на которые подписывается мост."""

    @abstractmethod
    def supports(self, envelope: EventEnvelope) -> bool:
        """Обрабатывает ли резолвер это событие."""

    @abstractmethod
    def resolve(self, envelope: EventEnvelope) -> tuple[str, dict[str, Any]]:
        """Вернуть топик и сообщение для подписчиков."""


class RealtimeBridge(IntegrationEventHandler):
    """Передаёт события из брокера в хаб процесса."""

    def __init__(self, hub: RealtimeHub, resolvers: Sequence[TopicResolver]) -> None:
        """Связать хаб и набор резолверов."""
        self._hub = hub
        self._resolvers = tuple(resolvers)

    @property
    def binding_keys(self) -> tuple[str, ...]:
        """Все ключи, нужные резолверам."""
        return tuple(dict.fromkeys(key for resolver in self._resolvers for key in resolver.binding_keys))

    async def handle(self, envelope: EventEnvelope) -> None:
        """Опубликовать сообщение каждого подходящего резолвера (одно событие — несколько топиков)."""
        for resolver in self._resolvers:
            if resolver.supports(envelope):
                topic, message = resolver.resolve(envelope)
                self._hub.publish(topic, message)
