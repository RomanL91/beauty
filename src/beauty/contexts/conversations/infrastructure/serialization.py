"""Содержимое сообщений ↔ JSON (колонка ``content``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.domain.content import (
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
    return {"kind": kind_of(content), **body}


def load_content(raw: dict[str, Any]) -> MessageContent:
    """JSON → VO."""
    kind = raw["kind"]
    if kind == "text":
        return TextContent(raw["text"])
    if kind == "voice":
        return VoiceContent(raw["audio_key"], float(raw["duration"]), raw.get("transcript"))
    if kind == "slot_offer":
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
    if kind == "booking_card":
        return BookingCardContent(UUID(raw["appointment_id"]), int(raw["revision"]), raw["appointment"])
    if kind == "system":
        return SystemContent(raw["text"], Tone(raw["tone"]))
    raise ValueError(f"Неизвестный вид сообщения: {kind!r}")
