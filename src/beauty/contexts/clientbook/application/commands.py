"""Команды Clientbook: имя клиента и заметки."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.clientbook.application.errors import ClientNoteNotFoundError, ClientNotFoundError
from beauty.contexts.clientbook.application.ports import Roster
from beauty.contexts.clientbook.application.uow import ClientbookUnitOfWork
from beauty.contexts.clientbook.domain.client_file import ClientFile, NoteAuthor
from beauty.contexts.clientbook.domain.errors import UnknownClientNote
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


class _FileHandler:
    """Общее: проверка клиента и карточка «загрузить или завести»."""

    def __init__(self, uow: ClientbookUnitOfWork, roster: Roster, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._roster = roster
        self._clock = clock
        self._ids = ids

    async def _file(self, uow: ClientbookUnitOfWork, master_id: UUID, client_id: UUID) -> ClientFile:
        found = await uow.files.get(master_id, client_id)
        if found is not None:
            return found
        if not await self._roster.has_client(master_id, client_id):
            raise ClientNotFoundError()
        created = ClientFile.open(
            file_id=self._ids.new(), master_id=master_id, client_id=client_id, now=self._clock.now()
        )
        uow.files.add(created)
        return created


@dataclass(frozen=True, slots=True)
class RenameClient(Command[None]):
    """Дать клиенту имя (``None`` — вернуть подпись по телефону)."""

    master_id: UUID
    client_id: UUID
    name: str | None


class RenameClientHandler(_FileHandler, Handler[RenameClient, None]):
    """Имя — в карточку; подпись в переписке и записях обновят подписчики события."""

    async def handle(self, message: RenameClient) -> None:
        """Переименовать."""
        async with self._uow as uow:
            client_file = await self._file(uow, message.master_id, message.client_id)
            client_file.rename(message.name, self._clock.now())
            await uow.commit()


@dataclass(frozen=True, slots=True)
class AddClientNote(Command[UUID]):
    """Заметка о клиенте от мастера или ИИ-администратора."""

    master_id: UUID
    client_id: UUID
    text: str
    by_agent: bool = False


class AddClientNoteHandler(_FileHandler, Handler[AddClientNote, UUID]):
    """Добавляет заметку (повтор текста — та же заметка)."""

    async def handle(self, message: AddClientNote) -> UUID:
        """Добавить и вернуть id заметки."""
        author = NoteAuthor.AGENT if message.by_agent else NoteAuthor.MASTER
        async with self._uow as uow:
            client_file = await self._file(uow, message.master_id, message.client_id)
            note = client_file.add_note(self._ids.new(), message.text, author, self._clock.now())
            await uow.commit()
            return note.id


@dataclass(frozen=True, slots=True)
class RemoveClientNote(Command[None]):
    """Удалить заметку (мастер — любую)."""

    master_id: UUID
    client_id: UUID
    note_id: UUID


class RemoveClientNoteHandler(Handler[RemoveClientNote, None]):
    """Удаляет заметку из карточки."""

    def __init__(self, uow: ClientbookUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: RemoveClientNote) -> None:
        """Удалить."""
        async with self._uow as uow:
            client_file = await uow.files.get(message.master_id, message.client_id)
            if client_file is None:
                raise ClientNoteNotFoundError()
            try:
                client_file.remove_note(message.note_id, self._clock.now())
            except UnknownClientNote as error:
                raise ClientNoteNotFoundError() from error
            await uow.commit()
