"""Карточка клиента: имя и заметки."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from beauty.contexts.clientbook.domain.client_file import MAX_NOTES, ClientFile, NoteAuthor
from beauty.contexts.clientbook.domain.errors import (
    ClientNotesLimit,
    InvalidClientName,
    InvalidClientNote,
    UnknownClientNote,
)
from beauty.contexts.clientbook.domain.events import ClientRenamed
from tests.fakes import FrozenClock


def new_file(clock: FrozenClock) -> ClientFile:
    return ClientFile.open(file_id=uuid4(), master_id=uuid4(), client_id=uuid4(), now=clock.now())


def test_rename_normalizes_and_records_event(clock: FrozenClock) -> None:
    client_file = new_file(clock)
    assert client_file.rename("  Айгерим   Н. ", clock.now())
    assert client_file.name == "Айгерим Н."
    assert not client_file.rename("Айгерим Н.", clock.now())  # то же имя — без события
    assert client_file.rename("   ", clock.now())  # пусто — снова подпись по телефону
    assert client_file.name is None
    events = [e for e in client_file.pull_events() if isinstance(e, ClientRenamed)]
    assert [e.name for e in events] == ["Айгерим Н.", None]
    assert events[0].client_id == client_file.client_id
    with pytest.raises(InvalidClientName):
        client_file.rename("я" * 61, clock.now())


def test_notes_dedupe_limit_and_remove(clock: FrozenClock) -> None:
    client_file = new_file(clock)
    first = client_file.add_note(uuid4(), "  Аллергия на лаванду ", NoteAuthor.AGENT, clock.now())
    again = client_file.add_note(uuid4(), "аллергия на лаванду", NoteAuthor.MASTER, clock.now())
    assert again is first  # повтор (без учёта регистра) — та же заметка
    assert (first.text, first.author) == ("Аллергия на лаванду", NoteAuthor.AGENT)
    clock.advance(timedelta(minutes=1))
    client_file.add_note(uuid4(), "Любит без музыки", NoteAuthor.MASTER, clock.now())
    assert client_file.updated_at == clock.now()
    client_file.remove_note(first.id, clock.now())
    assert [n.text for n in client_file.notes] == ["Любит без музыки"]
    with pytest.raises(UnknownClientNote):
        client_file.remove_note(first.id, clock.now())
    with pytest.raises(InvalidClientNote):
        client_file.add_note(uuid4(), " ", NoteAuthor.MASTER, clock.now())
    with pytest.raises(InvalidClientNote):
        client_file.add_note(uuid4(), "x" * 501, NoteAuthor.MASTER, clock.now())
    for i in range(MAX_NOTES - 1):
        client_file.add_note(uuid4(), f"Заметка {i}", NoteAuthor.MASTER, clock.now())
    with pytest.raises(ClientNotesLimit):
        client_file.add_note(uuid4(), "Лишняя", NoteAuthor.MASTER, clock.now())
