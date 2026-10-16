"""Read-модель переписки (SQL → DTO без агрегатов)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.conversations.application.dto import (
    ConversationView,
    FeedEntry,
    FeedRead,
    MessagePageView,
    MessageView,
)
from beauty.contexts.conversations.application.ports import ConversationReader
from beauty.contexts.conversations.infrastructure.tables import conversations, feed_events, messages

FEED_BATCH = 500
_MESSAGE_COLUMNS = (
    messages.c.id,
    messages.c.client_message_id,
    messages.c.author,
    messages.c.ai_generated,
    messages.c.created_at,
    messages.c.content,
)


def _view(row: Any) -> MessageView:
    return MessageView(
        id=row.id,
        client_message_id=row.client_message_id,
        author=row.author,
        ai_generated=row.ai_generated,
        created_at=row.created_at,
        content=row.content,
    )


class SqlConversationReader(ConversationReader):
    """История — по индексу ``(conversation_id, id)`` (UUIDv7 упорядочены по времени)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Получить фабрику сессий."""
        self._session_factory = session_factory

    async def find(self, master_id: UUID, client_id: UUID) -> ConversationView | None:
        """Переписка по паре."""
        statement = select(conversations.c.id, conversations.c.master_id).where(
            conversations.c.master_id == master_id, conversations.c.client_id == client_id
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
        return None if row is None else ConversationView(row.id, row.master_id)

    async def page(
        self, conversation_id: UUID, client_id: UUID, before: UUID | None, limit: int
    ) -> MessagePageView | None:
        """Последние ``limit`` сообщений старше ``before``."""
        async with self._session_factory() as session:
            if await self._last_seq(session, conversation_id, client_id) is None:
                return None
            statement = (
                select(*_MESSAGE_COLUMNS)
                .where(messages.c.conversation_id == conversation_id)
                .order_by(messages.c.id.desc())
                .limit(limit + 1)
            )
            if before is not None:
                statement = statement.where(messages.c.id < before)
            rows = (await session.execute(statement)).all()
        page = rows[:limit]
        return MessagePageView(tuple(_view(row) for row in reversed(page)), has_more=len(rows) > limit)

    async def feed(self, conversation_id: UUID, client_id: UUID, after: int | None) -> FeedRead | None:
        """События журнала после ``after`` с текущим состоянием сообщений."""
        async with self._session_factory() as session:
            last = await self._last_seq(session, conversation_id, client_id)
            if last is None:
                return None
            if after is None or after == last:
                return FeedRead((), last)
            if after > last or after < 0:
                return FeedRead((), last, reset=True)
            statement = (
                select(feed_events.c.seq, feed_events.c.change, *_MESSAGE_COLUMNS)
                .join(messages, messages.c.id == feed_events.c.message_id)
                .where(feed_events.c.conversation_id == conversation_id, feed_events.c.seq > after)
                .order_by(feed_events.c.seq)
                .limit(FEED_BATCH)
            )
            rows = (await session.execute(statement)).all()
        if not rows or rows[0].seq != after + 1:
            # Начало журнала уже удалено: досылать нечего, клиент перечитает историю.
            return FeedRead((), last, reset=True)
        entries = tuple(FeedEntry(row.seq, row.change, _view(row)) for row in rows)
        return FeedRead(entries, entries[-1].seq)

    @staticmethod
    async def _last_seq(session: AsyncSession, conversation_id: UUID, client_id: UUID) -> int | None:
        statement = select(conversations.c.last_event_seq).where(
            conversations.c.id == conversation_id, conversations.c.client_id == client_id
        )
        last: int | None = (await session.execute(statement)).scalar_one_or_none()
        return last
