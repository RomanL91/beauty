"""Содержимое ленты поручений ↔ JSON (колонка ``content``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from beauty.contexts.agent.domain.office import (
    ChoiceOption,
    OfficeBroadcast,
    OfficeChoice,
    OfficeContent,
    OfficeSystem,
    OfficeText,
    OfficeTone,
    OfficeVoice,
    office_kind,
)


def dump_office(content: OfficeContent) -> dict[str, Any]:
    """VO → JSON (с полем ``kind``)."""
    body: dict[str, Any]
    match content:
        case OfficeText(text):
            body = {"text": text}
        case OfficeVoice(audio_key, duration, transcript):
            body = {"audio_key": audio_key, "duration": duration, "transcript": transcript}
        case OfficeChoice(text, options, detail, selected):
            body = {
                "text": text,
                "detail": detail,
                "options": [{"id": o.id, "label": o.label, "muted": o.muted} for o in options],
                "selected_option_id": selected,
            }
        case OfficeSystem(text, tone):
            body = {"text": text, "tone": tone.value}
        case OfficeBroadcast(broadcast_id, text):
            body = {"broadcast_id": str(broadcast_id), "text": text}
    return {"kind": office_kind(content), **body}


def load_office(raw: dict[str, Any]) -> OfficeContent:
    """JSON → VO."""
    kind = raw["kind"]
    if kind == "text":
        return OfficeText(str(raw["text"]))
    if kind == "voice":
        transcript = raw.get("transcript")
        return OfficeVoice(
            str(raw["audio_key"]), float(raw["duration"]), None if transcript is None else str(transcript)
        )
    if kind == "choice":
        return OfficeChoice(
            str(raw["text"]),
            tuple(ChoiceOption(str(o["id"]), str(o["label"]), bool(o.get("muted"))) for o in raw["options"]),
            raw.get("detail"),
            raw.get("selected_option_id"),
        )
    if kind == "system":
        return OfficeSystem(str(raw["text"]), OfficeTone(raw["tone"]))
    if kind == "broadcast":
        return OfficeBroadcast(UUID(str(raw["broadcast_id"])), str(raw["text"]))
    raise ValueError(f"Неизвестный вид сообщения ленты поручений: {kind}")
