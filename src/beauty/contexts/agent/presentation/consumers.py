"""Консьюмеры Agent: клиент написал (ход ресепшна), мастер дал поручение или выбрал вариант
(ход кабинета), голосовое поручение — на расшифровку."""

from __future__ import annotations

from uuid import UUID

from beauty.contexts.agent.application.commands import AnswerClient
from beauty.contexts.agent.application.office import RunOfficeTurn, TranscribeOfficeTask
from beauty.contexts.agent.domain.events import OfficeChoiceAnswered, OfficeTaskGiven, OfficeVoiceTranscribed
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

CLIENT_MESSAGES = "conversations.client.message_posted"
VOICE_TRANSCRIBED = "conversations.voice.transcribed"
FRONT_DESK_EVENTS = (CLIENT_MESSAGES, VOICE_TRANSCRIBED)


class FrontDeskConsumer(IntegrationEventHandler):
    """Свободный текст → ход ресепшна; голосовое — когда Conversations его расшифрует
    (не вышло — ``text=None``, ход передаёт голосовое мастеру). Намерения записи
    обрабатывает Conversations."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Перевести событие в команду."""
        payload = envelope.payload
        if envelope.routing_key == VOICE_TRANSCRIBED:
            if payload.get("author") != "client":
                return
        elif payload.get("intent") != "text":
            return
        text = payload.get("text")
        await self._mediator.send(
            AnswerClient(
                conversation_id=UUID(str(payload["conversation_id"])),
                message_id=UUID(str(payload["message_id"])),
                text=None if text is None else str(text),
            )
        )


OFFICE_EVENTS = (
    OfficeTaskGiven.routing_key,
    OfficeChoiceAnswered.routing_key,
    OfficeVoiceTranscribed.routing_key,
)


class BackOfficeConsumer(IntegrationEventHandler):
    """Поручение, выбор мастера или расшифрованное голосовое поручение → ход кабинета."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Перевести событие в команду."""
        command = self.command(envelope)
        if command is not None:
            await self._mediator.send(command)

    @staticmethod
    def command(envelope: EventEnvelope) -> RunOfficeTurn | None:
        """Ход кабинета по событию; голосовое поручение ждёт расшифровки (``None``).

        Расшифровка не удалась — ``input=None``: агент попросит повторить или написать текстом.
        """
        payload = envelope.payload
        message_id = str(payload["message_id"])
        if envelope.routing_key == OfficeTaskGiven.routing_key and payload.get("text") is None:
            return None
        if envelope.routing_key == OfficeChoiceAnswered.routing_key:
            text: str | None = (
                f"Мастер выбрал «{payload['answer']}» в ответ на вопрос «{payload['question']}»."
            )
            key = f"{message_id}:choice"
        else:
            raw = payload.get("text")
            text = None if raw is None else str(raw)
            key = message_id
        return RunOfficeTurn(master_id=UUID(str(payload["master_id"])), input=text, idempotency_key=key)


class OfficeVoiceConsumer(IntegrationEventHandler):
    """Голосовое поручение → расшифровка."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Только голосовые (у текстового поручения есть ``text``)."""
        payload = envelope.payload
        if payload.get("text") is None:
            await self._mediator.send(
                TranscribeOfficeTask(UUID(str(payload["master_id"])), UUID(str(payload["message_id"])))
            )
