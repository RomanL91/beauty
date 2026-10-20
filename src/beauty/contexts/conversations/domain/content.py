"""Содержимое сообщений — value objects по видам.

Вид сообщения определяется типом содержимого; хранится одной JSON-колонкой.
Карточка заявки держит снимок записи из Booking (опубликованный язык Booking —
форма ``Appointment`` контракта) и его ревизию.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.domain.errors import InvalidMessage

MAX_TEXT = 4000
MAX_VOICE_SECONDS = 120.0


class Author(StrEnum):
    """Автор сообщения."""

    CLIENT = "client"
    AGENT = "agent"
    MASTER = "master"


class Tone(StrEnum):
    """Тон системного сообщения."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class TextContent:
    """Текст."""

    text: str

    def __post_init__(self) -> None:
        """Непустой и не длиннее лимита."""
        cleaned = self.text.strip()
        if not cleaned or len(cleaned) > MAX_TEXT:
            raise InvalidMessage(f"Текст — от 1 до {MAX_TEXT} символов")
        object.__setattr__(self, "text", cleaned)


@dataclass(frozen=True, slots=True)
class VoiceContent:
    """Голосовое: ключ файла в хранилище, длительность, расшифровка (позже)."""

    audio_key: str
    duration: float
    transcript: str | None = None

    def __post_init__(self) -> None:
        """Длительность в пределах лимита."""
        if not 0 < self.duration <= MAX_VOICE_SECONDS:
            raise InvalidMessage("Голосовое — до 2 минут")


@dataclass(frozen=True, slots=True)
class OfferedSlot:
    """Окно в предложении; время — в поясе мастера."""

    start: datetime
    end: datetime
    service_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SlotOfferContent:
    """Предложение окон; клиент выбирает одно."""

    text: str
    slots: tuple[OfferedSlot, ...]
    selected_start: datetime | None = None

    def __post_init__(self) -> None:
        """Хотя бы одно окно."""
        if not self.slots:
            raise InvalidMessage("В предложении нет окон")

    def find(self, start: datetime) -> OfferedSlot | None:
        """Окно, начинающееся в ``start`` (сравнение — по абсолютному времени)."""
        moment = start.astimezone(UTC)
        return next((s for s in self.slots if s.start.astimezone(UTC) == moment), None)


@dataclass(frozen=True, slots=True)
class BookingCardContent:
    """Карточка заявки: снимок записи из Booking и его ревизия."""

    appointment_id: UUID
    revision: int
    appointment: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class AgentNoteContent:
    """Заметка агента для мастера («клиент спрашивает про парковку») — клиенту не видна."""

    text: str

    def __post_init__(self) -> None:
        """Непустая и не длиннее лимита."""
        cleaned = self.text.strip()
        if not cleaned or len(cleaned) > MAX_TEXT:
            raise InvalidMessage(f"Заметка — от 1 до {MAX_TEXT} символов")
        object.__setattr__(self, "text", cleaned)


@dataclass(frozen=True, slots=True)
class SystemContent:
    """Системное сообщение («Запись подтверждена»)."""

    text: str
    tone: Tone = Tone.INFO


@dataclass(frozen=True, slots=True)
class AnnouncementContent:
    """Объявление мастера из рассылки: текст и фото (ключ файла в хранилище)."""

    text: str
    photo_key: str | None
    broadcast_id: UUID


type MessageContent = (
    TextContent
    | VoiceContent
    | SlotOfferContent
    | BookingCardContent
    | SystemContent
    | AgentNoteContent
    | AnnouncementContent
)

MASTER_ONLY_KINDS = frozenset({"agent_note"})
"""Виды сообщений, которые клиент не видит никогда."""


_KINDS: dict[type, str] = {
    TextContent: "text",
    VoiceContent: "voice",
    SlotOfferContent: "slot_offer",
    BookingCardContent: "booking_card",
    SystemContent: "system",
    AgentNoteContent: "agent_note",
    AnnouncementContent: "announcement",
}


def kind_of(content: MessageContent) -> str:
    """Вид сообщения в терминах контракта."""
    return _KINDS[type(content)]
