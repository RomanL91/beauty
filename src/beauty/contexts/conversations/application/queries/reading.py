"""Чтение переписки: поиск, история, лента событий."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.conversations.application.dto import FeedRead, MessagePageView, OpenedConversation
from beauty.contexts.conversations.application.errors import ConversationNotFoundError, MasterNotFoundError
from beauty.contexts.conversations.application.ports import ConversationReader, MasterCatalog
from beauty.shared.application.cqrs import Handler, Query

MAX_PAGE = 100


@dataclass(frozen=True, slots=True)
class GetMyConversation(Query[OpenedConversation]):
    """Переписка клиента с мастером, если она уже есть."""

    master_slug: str
    client_id: UUID


class GetMyConversationHandler(Handler[GetMyConversation, OpenedConversation]):
    """Мастер по адресу → переписка по паре (мастер, клиент)."""

    def __init__(self, reader: ConversationReader, catalog: MasterCatalog) -> None:
        """Получить зависимости."""
        self._reader = reader
        self._catalog = catalog

    async def handle(self, message: GetMyConversation) -> OpenedConversation:
        """Найти или ``ConversationNotFoundError``."""
        master = await self._catalog.by_slug(message.master_slug)
        if master is None:
            raise MasterNotFoundError()
        found = await self._reader.find(master.id, message.client_id)
        if found is None:
            raise ConversationNotFoundError()
        return OpenedConversation(found.id, master.slug, created=False)


@dataclass(frozen=True, slots=True)
class ListMessages(Query[MessagePageView]):
    """Страница истории: сообщения старше ``before`` (или последние)."""

    conversation_id: UUID
    client_id: UUID
    before: UUID | None = None
    limit: int = 30


class ListMessagesHandler(Handler[ListMessages, MessagePageView]):
    """Читает историю из read-модели."""

    def __init__(self, reader: ConversationReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: ListMessages) -> MessagePageView:
        """Страница или ``ConversationNotFoundError``."""
        limit = max(1, min(message.limit, MAX_PAGE))
        page = await self._reader.page(message.conversation_id, message.client_id, message.before, limit)
        if page is None:
            raise ConversationNotFoundError()
        return page


@dataclass(frozen=True, slots=True)
class ReadFeed(Query[FeedRead]):
    """События ленты после ``after``; ``None`` — только текущая позиция."""

    conversation_id: UUID
    client_id: UUID
    after: int | None = None


class ReadFeedHandler(Handler[ReadFeed, FeedRead]):
    """Читает журнал ленты."""

    def __init__(self, reader: ConversationReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: ReadFeed) -> FeedRead:
        """События или ``ConversationNotFoundError``."""
        feed = await self._reader.feed(message.conversation_id, message.client_id, message.after)
        if feed is None:
            raise ConversationNotFoundError()
        return feed
