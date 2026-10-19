"""Доменные события Agent: лента поручений мастера."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from beauty.shared.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class OfficeFeedChanged(DomainEvent):
    """В ленте поручений появилось или изменилось сообщение (будит поток кабинета).

    ``message`` — снимок в форме контракта (голосовое — с ключом файла вместо ссылки).
    """

    routing_key = "agent.office.feed_changed"

    master_id: UUID
    message_id: UUID
    change: str
    message: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class OfficeTaskGiven(DomainEvent):
    """Мастер дал поручение (``text=None`` — голосовое): агенту на ход."""

    routing_key = "agent.office.task_given"

    master_id: UUID
    message_id: UUID
    text: str | None


@dataclass(frozen=True, kw_only=True)
class OfficeChoiceAnswered(DomainEvent):
    """Мастер выбрал вариант в карточке агента: агенту на ход."""

    routing_key = "agent.office.choice_answered"

    master_id: UUID
    message_id: UUID
    question: str
    answer: str


@dataclass(frozen=True, kw_only=True)
class OfficeVoiceTranscribed(DomainEvent):
    """Голосовое поручение расшифровано (``text=None`` — не вышло): агенту на ход."""

    routing_key = "agent.office.voice_transcribed"

    master_id: UUID
    message_id: UUID
    text: str | None
