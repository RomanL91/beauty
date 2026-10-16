"""Консьюмер Agent: клиент написал свободный текст или голосовое."""

from __future__ import annotations

from uuid import UUID

from beauty.contexts.agent.application.commands import AnswerClient
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

CLIENT_MESSAGES = "conversations.client.message_posted"
AGENT_INTENTS = frozenset({"text", "voice"})


class FrontDeskConsumer(IntegrationEventHandler):
    """Свободный текст и голосовые → ход ресепшна (намерения записи обрабатывает Conversations)."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Перевести событие в команду."""
        payload = envelope.payload
        if payload.get("intent") not in AGENT_INTENTS:
            return
        text = payload.get("text")
        await self._mediator.send(
            AnswerClient(
                conversation_id=UUID(str(payload["conversation_id"])),
                message_id=UUID(str(payload["message_id"])),
                text=None if text is None else str(text),
            )
        )
