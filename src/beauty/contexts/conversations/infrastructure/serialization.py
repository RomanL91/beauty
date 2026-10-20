"""Содержимое сообщений ↔ JSON (колонка ``content``)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.domain.content import (
    AgentNoteContent,
    AnnouncementContent,
    BookingCardContent,
    MessageContent,
    OfferedSlot,
    SlotOfferContent,
    SystemContent,
    TextContent,
    Tone,
    VoiceContent,
    kind_of,
)


def _slot(slot: OfferedSlot) -> dict[str, Any]:
    return {
        "start": slot.start.isoformat(),
        "end": slot.end.isoformat(),
        "service_id": None if slot.service_id is None else str(slot.service_id),
    }


def dump_content(content: MessageContent) -> dict[str, Any]:
    """VO → JSON (с полем ``kind``)."""
    body: dict[str, Any]
    match content:
        case TextContent(text):
            body = {"text": text}
        case VoiceContent(audio_key, duration, transcript):
            body = {"audio_key": audio_key, "duration": duration, "transcript": transcript}
        case SlotOfferContent(text, slots, selected):
            body = {
                "text": text,
                "slots": [_slot(slot) for slot in slots],
                "selected_start": None if selected is None else selected.isoformat(),
            }
        case BookingCardContent(appointment_id, revision, appointment):
            body = {
                "appointment_id": str(appointment_id),
                "revision": revision,
                "appointment": dict(appointment),
            }
        case SystemContent(text, tone):
            body = {"text": text, "tone": tone.value}
        case AgentNoteContent(text):
            body = {"text": text}
        case AnnouncementContent(text, photo_key, broadcast_id):
            body = {"text": text, "photo_key": photo_key, "broadcast_id": str(broadcast_id)}
    return {"kind": kind_of(content), **body}


def _slot_offer(raw: dict[str, Any]) -> SlotOfferContent:
    selected = raw.get("selected_start")
    return SlotOfferContent(
        raw["text"],
        tuple(
            OfferedSlot(
                datetime.fromisoformat(slot["start"]),
                datetime.fromisoformat(slot["end"]),
                None if slot.get("service_id") is None else UUID(slot["service_id"]),
            )
            for slot in raw["slots"]
        ),
        None if selected is None else datetime.fromisoformat(selected),
    )


_LOADERS: dict[str, Callable[[dict[str, Any]], MessageContent]] = {
    "text": lambda raw: TextContent(raw["text"]),
    "voice": lambda raw: VoiceContent(raw["audio_key"], float(raw["duration"]), raw.get("transcript")),
    "slot_offer": _slot_offer,
    "booking_card": lambda raw: BookingCardContent(
        UUID(raw["appointment_id"]), int(raw["revision"]), raw["appointment"]
    ),
    "system": lambda raw: SystemContent(raw["text"], Tone(raw["tone"])),
    "agent_note": lambda raw: AgentNoteContent(raw["text"]),
    "announcement": lambda raw: AnnouncementContent(
        raw["text"], raw.get("photo_key"), UUID(raw["broadcast_id"])
    ),
}


def load_content(raw: dict[str, Any]) -> MessageContent:
    """JSON → VO."""
    loader = _LOADERS.get(raw["kind"])
    if loader is None:
        raise ValueError(f"Неизвестный вид сообщения: {raw['kind']!r}")
    return loader(raw)
