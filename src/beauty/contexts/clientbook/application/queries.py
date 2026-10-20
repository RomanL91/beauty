"""Запросы Clientbook: список, карточка, заметки и имя клиента."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.clientbook.application.dto import ClientCardView, ClientPage, NoteView
from beauty.contexts.clientbook.application.errors import ClientNotFoundError
from beauty.contexts.clientbook.application.ports import ClientbookReader
from beauty.shared.application.cqrs import Handler, Query
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class ListClients(Query[ClientPage]):
    """Клиенты мастера: поиск по имени или цифрам телефона, «только с записью впереди»."""

    master_id: UUID
    query: str | None = None
    upcoming_only: bool = False
    limit: int = 30
    offset: int = 0


class ListClientsHandler(Handler[ListClients, ClientPage]):
    """Страница из read-модели."""

    def __init__(self, reader: ClientbookReader, clock: Clock) -> None:
        """Получить read-модель и часы."""
        self._reader = reader
        self._clock = clock

    async def handle(self, message: ListClients) -> ClientPage:
        """Страница."""
        query = (message.query or "").strip() or None
        return await self._reader.page(
            message.master_id, query, message.upcoming_only, message.limit, message.offset, self._clock.now()
        )


@dataclass(frozen=True, slots=True)
class GetClientCard(Query[ClientCardView]):
    """Карточка клиента."""

    master_id: UUID
    client_id: UUID


class GetClientCardHandler(Handler[GetClientCard, ClientCardView]):
    """Карточка или ``client_not_found``."""

    def __init__(self, reader: ClientbookReader, clock: Clock) -> None:
        """Получить read-модель и часы."""
        self._reader = reader
        self._clock = clock

    async def handle(self, message: GetClientCard) -> ClientCardView:
        """Карточка."""
        card = await self._reader.card(message.master_id, message.client_id, self._clock.now())
        if card is None:
            raise ClientNotFoundError()
        return card


@dataclass(frozen=True, slots=True)
class ListClientNotes(Query[list[NoteView]]):
    """Заметки о клиенте (для агента)."""

    master_id: UUID
    client_id: UUID


class ListClientNotesHandler(Handler[ListClientNotes, list[NoteView]]):
    """Заметки, свежие сверху."""

    def __init__(self, reader: ClientbookReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: ListClientNotes) -> list[NoteView]:
        """Заметки."""
        return await self._reader.notes(message.master_id, message.client_id)


@dataclass(frozen=True, slots=True)
class GetClientName(Query[str | None]):
    """Имя клиента у мастера (для новых заявок Booking)."""

    master_id: UUID
    client_id: UUID


class GetClientNameHandler(Handler[GetClientName, str | None]):
    """Имя или ``None``."""

    def __init__(self, reader: ClientbookReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: GetClientName) -> str | None:
        """Имя."""
        return await self._reader.name(message.master_id, message.client_id)
