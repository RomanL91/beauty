"""Сообщения → JSON контракта (``Message``)."""

from __future__ import annotations

from typing import Any

from beauty.contexts.conversations.application.dto import MessageView
from beauty.contexts.conversations.domain.content import (
    BookingCardContent,
    OfferedSlot,
    SlotOfferContent,
    SystemContent,
    TextContent,
    VoiceContent,
    kind_of,
)
from beauty.shared.infrastructure.storage.signing import SignedMediaUrls


class MessageRenderer:
    """Форма сообщения в API; ссылки на голосовые — подписанные."""

    def __init__(self, media: SignedMediaUrls) -> None:
        """Получить подписчика ссылок."""
        self._media = media

    def render(self, message: MessageView) -> dict[str, Any]:
        """Сообщение в форме контракта."""
        content = message.content
        payload: dict[str, Any] = {
            "id": str(message.id),
            "client_id": None if message.client_message_id is None else str(message.client_message_id),
            "author": message.author.value,
            "ai_generated": message.ai_generated,
            "sources": [],
            "created_at": message.created_at.isoformat(),
            "kind": kind_of(content),
        }
        match content:
            case TextContent(text):
                payload["text"] = text
            case VoiceContent(audio_key, duration, transcript):
                payload |= {
                    "audio_url": self._media.url(audio_key),
                    "duration": duration,
                    "transcript": transcript,
                }
            case SlotOfferContent(text, slots, selected):
                payload |= {
                    "text": text,
                    "slots": [_slot(slot) for slot in slots],
                    "selected_start": None if selected is None else selected.isoformat(),
                }
            case BookingCardContent(_, _, appointment):
                payload["appointment"] = dict(appointment)
            case SystemContent(text, tone):
                payload |= {"text": text, "tone": tone.value}
        return payload


def _slot(slot: OfferedSlot) -> dict[str, Any]:
    rendered: dict[str, Any] = {"start": slot.start.isoformat(), "end": slot.end.isoformat()}
    if slot.service_id is not None:
        rendered["service_id"] = str(slot.service_id)
    return rendered
