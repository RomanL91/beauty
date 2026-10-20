"""Агрегат ``ClientFile`` — карточка клиента у мастера: имя и заметки.

Карточка заводится при первом изменении (имя или заметка); у клиента без карточки нет ни
имени, ни заметок. Заметки — короткие факты («аллергия на лаванду»): пишет мастер или
ИИ-администратор, удаляет только мастер. Тот же текст повторно новой заметки не создаёт —
агент склонен записывать одно и то же из хода в ход.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from beauty.contexts.clientbook.domain.errors import (
    ClientNotesLimit,
    InvalidClientName,
    InvalidClientNote,
    UnknownClientNote,
)
from beauty.contexts.clientbook.domain.events import ClientRenamed
from beauty.shared.domain.aggregate import AggregateRoot, Entity

MAX_NAME = 60
MAX_NOTE = 500
MAX_NOTES = 100


class NoteAuthor(StrEnum):
    """Кто записал заметку."""

    MASTER = "master"
    AGENT = "agent"


class ClientNote(Entity):
    """Заметка о клиенте."""

    def __init__(self, note_id: UUID, text: str, author: NoteAuthor, created_at: datetime) -> None:
        """Создать заметку (только через ``ClientFile.add_note``)."""
        self.id = note_id
        self.text = text
        self.author = author
        self.created_at = created_at


def normalize_name(name: str | None) -> str | None:
    """Пробелы схлопнуты; пусто — ``None`` (подпись по телефону)."""
    cleaned = " ".join((name or "").split())
    if len(cleaned) > MAX_NAME:
        raise InvalidClientName()
    return cleaned or None


def normalize_note(text: str) -> str:
    """Обрезанный текст заметки в пределах лимита."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_NOTE:
        raise InvalidClientNote()
    return cleaned


class ClientFile(AggregateRoot):
    """Карточка клиента у мастера (одна на пару «мастер, клиент»)."""

    def __init__(self, file_id: UUID, master_id: UUID, client_id: UUID, created_at: datetime) -> None:
        """Создать карточку (используйте ``open``)."""
        self.id = file_id
        self.master_id = master_id
        self.client_id = client_id
        self.name: str | None = None
        self.notes: list[ClientNote] = []
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def open(cls, *, file_id: UUID, master_id: UUID, client_id: UUID, now: datetime) -> ClientFile:
        """Завести карточку."""
        return cls(file_id, master_id, client_id, now)

    def rename(self, name: str | None, now: datetime) -> bool:
        """Дать имя (``None`` или пусто — подпись по телефону); то же имя — no-op (``False``)."""
        cleaned = normalize_name(name)
        if cleaned == self.name:
            return False
        self.name = cleaned
        self.updated_at = now
        self._record(
            ClientRenamed(occurred_at=now, master_id=self.master_id, client_id=self.client_id, name=cleaned)
        )
        return True

    def add_note(self, note_id: UUID, text: str, author: NoteAuthor, now: datetime) -> ClientNote:
        """Добавить заметку; такая уже есть (без учёта регистра) — вернуть её."""
        cleaned = normalize_note(text)
        same = next((n for n in self.notes if n.text.casefold() == cleaned.casefold()), None)
        if same is not None:
            return same
        if len(self.notes) >= MAX_NOTES:
            raise ClientNotesLimit()
        note = ClientNote(note_id, cleaned, author, now)
        self.notes.append(note)
        self.updated_at = now
        return note

    def remove_note(self, note_id: UUID, now: datetime) -> None:
        """Удалить заметку."""
        note = next((n for n in self.notes if n.id == note_id), None)
        if note is None:
            raise UnknownClientNote()
        self.notes.remove(note)
        self.updated_at = now
