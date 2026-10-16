"""Чаты мастера."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.conversations.application.dto import (
    ConversationSummaryView,
    InboxView,
    MessagePageView,
    MessageView,
)
from beauty.contexts.conversations.application.errors import ConversationNotFoundError
from beauty.contexts.conversations.application.ports import InboxReader
from beauty.contexts.conversations.application.queries.reading import MAX_PAGE
from beauty.shared.application.cqrs import Handler, Query

FILTERS = frozenset({"all", "needs_me", "agent", "me"})


@dataclass(frozen=True, slots=True)
class ListInbox(Query[InboxView]):
    """Чаты мастера: «нужны вы» сверху, затем по последнему сообщению."""

    master_id: UUID
    filter_by: str = "all"
    query: str | None = None


class ListInboxHandler(Handler[ListInbox, InboxView]):
    """Читает список из read-модели."""

    def __init__(self, reader: InboxReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: ListInbox) -> InboxView:
        """Список (неизвестный фильтр — как ``all``)."""
        filter_by = message.filter_by if message.filter_by in FILTERS else "all"
        query = (message.query or "").strip()[:100] or None
        return await self._reader.inbox(message.master_id, filter_by, query)


@dataclass(frozen=True, slots=True)
class GetConversationSummary(Query[ConversationSummaryView]):
    """Шапка диалога."""

    master_id: UUID
    conversation_id: UUID


class GetConversationSummaryHandler(Handler[GetConversationSummary, ConversationSummaryView]):
    """Читает сводку из read-модели."""

    def __init__(self, reader: InboxReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: GetConversationSummary) -> ConversationSummaryView:
        """Сводка или ``ConversationNotFoundError``."""
        found = await self._reader.summary(message.master_id, message.conversation_id)
        if found is None:
            raise ConversationNotFoundError()
        return found


@dataclass(frozen=True, slots=True)
class ListMasterMessages(Query[MessagePageView]):
    """История диалога глазами мастера."""

    conversation_id: UUID
    master_id: UUID
    before: UUID | None = None
    limit: int = 30


class ListMasterMessagesHandler(Handler[ListMasterMessages, MessagePageView]):
    """Читает историю из read-модели."""

    def __init__(self, reader: InboxReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: ListMasterMessages) -> MessagePageView:
        """Страница или ``ConversationNotFoundError``."""
        limit = max(1, min(message.limit, MAX_PAGE))
        page = await self._reader.master_page(
            message.conversation_id, message.master_id, message.before, limit
        )
        if page is None:
            raise ConversationNotFoundError()
        return page


@dataclass(frozen=True, slots=True)
class GetMasterMessage(Query[tuple[UUID, MessageView] | None]):
    """Сообщение переписки мастера (``None`` — нет или чужое)."""

    master_id: UUID
    message_id: UUID


class GetMasterMessageHandler(Handler[GetMasterMessage, tuple[UUID, MessageView] | None]):
    """Читает сообщение из read-модели."""

    def __init__(self, reader: InboxReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: GetMasterMessage) -> tuple[UUID, MessageView] | None:
        """Переписка и сообщение."""
        return await self._reader.master_message(message.master_id, message.message_id)
