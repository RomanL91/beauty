"""Модуль контекста Clientbook: клиентская картотека мастера."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.clientbook.application.commands import (
    AddClientNote,
    AddClientNoteHandler,
    RemoveClientNote,
    RemoveClientNoteHandler,
    RenameClient,
    RenameClientHandler,
)
from beauty.contexts.clientbook.application.ports import Roster
from beauty.contexts.clientbook.application.queries import (
    GetClientCard,
    GetClientCardHandler,
    GetClientName,
    GetClientNameHandler,
    ListClientNotes,
    ListClientNotesHandler,
    ListClients,
    ListClientsHandler,
)
from beauty.contexts.clientbook.infrastructure.mapping import ClientbookOrmMapper
from beauty.contexts.clientbook.infrastructure.reader import SqlClientbookReader
from beauty.contexts.clientbook.infrastructure.uow import SqlAlchemyClientbookUnitOfWork
from beauty.contexts.clientbook.presentation.api import clients_router
from beauty.shared.application.mediator import Mediator
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.web.auth import MasterAuth
from beauty.shared.infrastructure.web.errors import HttpErrorMapper

_HTTP_STATUSES: dict[str, int] = {
    "client_not_found": 404,
    "client_note_not_found": 404,
    "invalid_client_name": 422,
    "invalid_client_note": 422,
    "client_notes_limit": 409,
}


@dataclass(frozen=True, slots=True)
class ClientbookDependencies:
    """Зависимости картотеки."""

    session_factory: async_sessionmaker[AsyncSession]
    outbox_writer: OutboxWriter
    clock: Clock
    ids: IdGenerator
    roster: Roster


class ClientbookModule:
    """Сборка контекста Clientbook."""

    def __init__(self, dependencies: ClientbookDependencies) -> None:
        """Создать долгоживущие компоненты."""
        ClientbookOrmMapper.map()
        self._deps = dependencies
        self._reader = SqlClientbookReader(dependencies.session_factory)

    def register(self, mediator: Mediator, http_errors: HttpErrorMapper) -> None:
        """Зарегистрировать обработчики и коды ошибок."""
        deps, reader = self._deps, self._reader
        files = (deps.roster, deps.clock, deps.ids)
        mediator.register(RenameClient, lambda: RenameClientHandler(self._uow(), *files))
        mediator.register(AddClientNote, lambda: AddClientNoteHandler(self._uow(), *files))
        mediator.register(RemoveClientNote, lambda: RemoveClientNoteHandler(self._uow(), deps.clock))
        mediator.register(ListClients, lambda: ListClientsHandler(reader, deps.clock))
        mediator.register(GetClientCard, lambda: GetClientCardHandler(reader, deps.clock))
        mediator.register(ListClientNotes, lambda: ListClientNotesHandler(reader))
        mediator.register(GetClientName, lambda: GetClientNameHandler(reader))
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def cabinet_router(self, mediator: Mediator, auth: MasterAuth) -> APIRouter:
        """``/me/clients``."""
        return clients_router(mediator, auth)

    def _uow(self) -> SqlAlchemyClientbookUnitOfWork:
        """Новый Unit of Work."""
        return SqlAlchemyClientbookUnitOfWork(self._deps.session_factory, self._deps.outbox_writer)
