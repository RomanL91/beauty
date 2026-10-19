"""Расшифровка голосового в переписке.

Голосовое попадает в ленту сразу; текст приходит позже — обновлением того же
сообщения. Итог (текст или неудача) — событие ``VoiceTranscribed``: по нему отвечает
ИИ-администратор. Распознавание — внешний сервис, поэтому оно идёт между двумя
короткими транзакциями, а не внутри одной.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.conversations.application.commands.base import load_conversation
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.content import VoiceContent
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.application.speech import VoiceTranscriber
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class TranscribeVoice(Command[None]):
    """Расшифровать голосовое сообщение (из события ``MessageAdded``)."""

    message_id: UUID


class TranscribeVoiceHandler(Handler[TranscribeVoice, None]):
    """Файл → сервис распознавания → текст в сообщение; повтор уже расшифрованного — no-op."""

    def __init__(
        self,
        uow_factory: Callable[[], ConversationsUnitOfWork],
        transcriber: VoiceTranscriber,
        clock: Clock,
    ) -> None:
        """Получить зависимости."""
        self._uow_factory = uow_factory
        self._transcriber = transcriber
        self._clock = clock

    async def handle(self, message: TranscribeVoice) -> None:
        """Расшифровать и сообщить итог."""
        async with self._uow_factory() as uow:
            voice = await uow.messages.get(message.message_id)
        if (
            voice is None
            or not isinstance(voice.content, VoiceContent)
            or voice.content.transcript is not None
        ):
            return
        transcript = await self._transcriber.transcript(voice.content.audio_key)
        async with self._uow_factory() as uow:
            stored = await uow.messages.get(message.message_id)
            if stored is None or not isinstance(stored.content, VoiceContent) or stored.content.transcript:
                return
            conversation = await load_conversation(uow, stored.conversation_id)
            conversation.voice_transcribed(stored, transcript, self._clock.now())
            await uow.commit()
