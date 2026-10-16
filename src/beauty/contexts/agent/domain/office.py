"""Лента поручений — рабочий канал мастера с его ИИ-администратором («кабинет»).

Мастер даёт поручения текстом или голосом, агент отвечает текстом, карточкой выбора
(``choice``) или служебной строкой. Сообщение — отдельный агрегат: выбор варианта меняет
только карточку. Снимок сообщения (``snapshot``) — в форме контракта ``Message``, кроме
голосового: вместо ссылки — ключ файла (ссылку подписывает слой представления).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from beauty.contexts.agent.domain.errors import ChoiceAlreadyAnswered, UnknownChoiceOption
from beauty.contexts.agent.domain.events import OfficeChoiceAnswered, OfficeFeedChanged, OfficeTaskGiven
from beauty.shared.domain.aggregate import AggregateRoot

MAX_OPTIONS = 4


class OfficeAuthor(StrEnum):
    """Кто написал в ленту поручений."""

    MASTER = "master"
    AGENT = "agent"


class OfficeTone(StrEnum):
    """Тон служебной строки."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class OfficeText:
    """Текст."""

    text: str


@dataclass(frozen=True, slots=True)
class OfficeVoice:
    """Голосовое мастера (расшифровки пока нет)."""

    audio_key: str
    duration: float


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    """Вариант ответа."""

    id: str
    label: str
    muted: bool = False


@dataclass(frozen=True, slots=True)
class OfficeChoice:
    """Вопрос агента мастеру с вариантами."""

    text: str
    options: tuple[ChoiceOption, ...]
    detail: str | None = None
    selected_option_id: str | None = None

    def option(self, option_id: str) -> ChoiceOption:
        """Вариант по id или ``UnknownChoiceOption``."""
        for option in self.options:
            if option.id == option_id:
                return option
        raise UnknownChoiceOption()


@dataclass(frozen=True, slots=True)
class OfficeSystem:
    """Служебная строка (поручение не выполнено, агент не подключён)."""

    text: str
    tone: OfficeTone = OfficeTone.INFO


type OfficeContent = OfficeText | OfficeVoice | OfficeChoice | OfficeSystem


def office_kind(content: OfficeContent) -> str:
    """Вид сообщения в контракте."""
    match content:
        case OfficeText():
            return "text"
        case OfficeVoice():
            return "voice"
        case OfficeChoice():
            return "choice"
        case OfficeSystem():
            return "system"


def choice(question: str, labels: list[str], detail: str | None = None) -> OfficeChoice:
    """Карточка выбора: варианты нумеруются по порядку, последний «ничего не менять» — приглушён."""
    cleaned = [label.strip() for label in labels if label.strip()]
    if not question.strip() or not 2 <= len(cleaned) <= MAX_OPTIONS:
        raise ValueError(f"Нужен вопрос и от 2 до {MAX_OPTIONS} вариантов")
    options = tuple(
        ChoiceOption(str(number), label, muted=label.lower().startswith("ничего"))
        for number, label in enumerate(cleaned, start=1)
    )
    return OfficeChoice(question.strip(), options, detail.strip() if detail and detail.strip() else None)


class OfficeMessage(AggregateRoot):
    """Сообщение ленты поручений мастера."""

    def __init__(
        self,
        message_id: UUID,
        master_id: UUID,
        author: OfficeAuthor,
        content: OfficeContent,
        client_message_id: UUID | None,
        ai_generated: bool,
        created_at: datetime,
    ) -> None:
        """Создать сообщение (используйте ``from_master`` / ``from_agent``)."""
        self.id = message_id
        self.master_id = master_id
        self.author = author
        self.content = content
        self.kind = office_kind(content)
        self.client_message_id = client_message_id
        self.ai_generated = ai_generated
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def from_master(
        cls,
        *,
        message_id: UUID,
        master_id: UUID,
        client_message_id: UUID,
        content: OfficeText | OfficeVoice,
        now: datetime,
    ) -> OfficeMessage:
        """Поручение мастера: в ленту и агенту на ход."""
        message = cls(message_id, master_id, OfficeAuthor.MASTER, content, client_message_id, False, now)
        message._changed("message.created", now)
        message._record(
            OfficeTaskGiven(
                occurred_at=now,
                master_id=master_id,
                message_id=message_id,
                text=content.text if isinstance(content, OfficeText) else None,
            )
        )
        return message

    @classmethod
    def from_agent(
        cls, *, message_id: UUID, master_id: UUID, content: OfficeContent, now: datetime
    ) -> OfficeMessage:
        """Ответ агента (служебная строка — без пометки ИИ)."""
        message = cls(
            message_id,
            master_id,
            OfficeAuthor.AGENT,
            content,
            None,
            not isinstance(content, OfficeSystem),
            now,
        )
        message._changed("message.created", now)
        return message

    def choose(self, option_id: str, now: datetime) -> bool:
        """Мастер выбрал вариант; тот же повторно — no-op (``False``), другой — ``ChoiceAlreadyAnswered``."""
        content = self.content
        if not isinstance(content, OfficeChoice):
            raise UnknownChoiceOption()
        option = content.option(option_id)
        if content.selected_option_id == option_id:
            return False
        if content.selected_option_id is not None:
            raise ChoiceAlreadyAnswered()
        self.content = OfficeChoice(content.text, content.options, content.detail, option_id)
        self.updated_at = now
        self._changed("message.updated", now)
        self._record(
            OfficeChoiceAnswered(
                occurred_at=now,
                master_id=self.master_id,
                message_id=self.id,
                question=content.text,
                answer=option.label,
            )
        )
        return True

    def snapshot(self) -> dict[str, Any]:
        """Сообщение в форме контракта (голосовое — с ``audio_key`` вместо ссылки)."""
        payload: dict[str, Any] = {
            "id": str(self.id),
            "client_id": None if self.client_message_id is None else str(self.client_message_id),
            "author": self.author.value,
            "ai_generated": self.ai_generated,
            "sources": [],
            "created_at": self.created_at.isoformat(),
            "kind": self.kind,
        }
        match self.content:
            case OfficeText(text):
                payload["text"] = text
            case OfficeVoice(audio_key, duration):
                payload |= {"audio_key": audio_key, "duration": duration, "transcript": None}
            case OfficeChoice(text, options, detail, selected):
                payload |= {
                    "choice_id": str(self.id),
                    "text": text,
                    "options": [
                        {"id": o.id, "label": o.label, "tone": "muted" if o.muted else "default"}
                        for o in options
                    ],
                    "selected_option_id": selected,
                }
                if detail:
                    payload["detail"] = detail
            case OfficeSystem(text, tone):
                payload |= {"text": text, "tone": tone.value}
        return payload

    def _changed(self, change: str, now: datetime) -> None:
        self._record(
            OfficeFeedChanged(
                occurred_at=now,
                master_id=self.master_id,
                message_id=self.id,
                change=change,
                message=self.snapshot(),
            )
        )
