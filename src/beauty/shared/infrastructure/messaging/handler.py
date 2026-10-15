"""Контракт обработчика интеграционного события."""

from __future__ import annotations

from abc import ABC, abstractmethod

from beauty.shared.infrastructure.outbox.envelope import EventEnvelope


class IntegrationEventHandler(ABC):
    """Обработчик события, пришедшего из брокера.

    Обычно он лишь переводит событие в команду своего контекста и отправляет её в
    медиатор — логика остаётся в прикладном слое контекста.
    """

    @abstractmethod
    async def handle(self, envelope: EventEnvelope) -> None:
        """Обработать событие; исключение означает «повторить позже»."""
