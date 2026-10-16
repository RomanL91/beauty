"""Консьюмеры Agent: клиент написал (ход ресепшна), мастер дал поручение или выбрал вариант (ход кабинета)."""

from __future__ import annotations

from uuid import UUID

from beauty.contexts.agent.application.commands import AnswerClient
from beauty.contexts.agent.application.office import RunOfficeTurn
from beauty.contexts.agent.domain.events import OfficeChoiceAnswered, OfficeTaskGiven
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


OFFICE_EVENTS = (OfficeTaskGiven.routing_key, OfficeChoiceAnswered.routing_key)


class BackOfficeConsumer(IntegrationEventHandler):
    """Поручение или выбор мастера → ход кабинета."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Перевести событие в команду."""
        payload = envelope.payload
        master_id = UUID(str(payload["master_id"]))
        message_id = str(payload["message_id"])
        if envelope.routing_key == OfficeChoiceAnswered.routing_key:
            text: str | None = (
                f"Мастер выбрал «{payload['answer']}» в ответ на вопрос «{payload['question']}»."
            )
            key = f"{message_id}:choice"
        else:
            raw = payload.get("text")
            text = None if raw is None else str(raw)
            key = message_id
        await self._mediator.send(RunOfficeTurn(master_id=master_id, input=text, idempotency_key=key))
