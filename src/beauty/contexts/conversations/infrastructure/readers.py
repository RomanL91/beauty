"""Read-модель переписки (SQL → DTO без агрегатов)."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.conversations.application.dto import (
    ConversationState,
    ConversationSummaryView,
    ConversationView,
    FeedEntry,
    FeedRead,
    InboxView,
    LastMessageView,
    MessagePageView,
    MessageView,
)
from beauty.contexts.conversations.application.ports import ConversationReader, InboxReader
from beauty.contexts.conversations.domain.content import MASTER_ONLY_KINDS
from beauty.contexts.conversations.domain.conversation import Handler
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

    async def state(self, conversation_id: UUID) -> ConversationState | None:
        """Мастер, клиент и обработчик."""
        c = conversations.c
        statement = select(c.id, c.master_id, c.client_id, c.client_display_name, c.handler).where(
            c.id == conversation_id
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        return ConversationState(
            row.id, row.master_id, row.client_id, row.client_display_name, row.handler.value
        )

    async def ids_for(self, master_id: UUID, client_ids: frozenset[UUID]) -> dict[UUID, UUID]:
        """Переписки мастера с этими клиентами (уникальный индекс пары)."""
        if not client_ids:
            return {}
        statement = select(conversations.c.client_id, conversations.c.id).where(
            conversations.c.master_id == master_id, conversations.c.client_id.in_(client_ids)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return {row.client_id: row.id for row in rows}

    async def page(
        self, conversation_id: UUID, client_id: UUID, before: UUID | None, limit: int
    ) -> MessagePageView | None:
        """Последние ``limit`` сообщений старше ``before``."""
        async with self._session_factory() as session:
            if await self._last_seq(session, conversation_id, client_id) is None:
                return None
        return await self.history(conversation_id, before, limit, for_master=False)

    async def history(
        self, conversation_id: UUID, before: UUID | None, limit: int, *, for_master: bool
    ) -> MessagePageView:
        """Последние ``limit`` сообщений старше ``before`` (доступ проверяет вызывающий).

        Клиенту не отдаются сообщения только для мастера (заметки агента).
        """
        async with self._session_factory() as session:
            statement = (
                select(*_MESSAGE_COLUMNS)
                .where(messages.c.conversation_id == conversation_id)
                .order_by(messages.c.id.desc())
                .limit(limit + 1)
            )
            if not for_master:
                statement = statement.where(messages.c.kind.not_in(MASTER_ONLY_KINDS))
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
                select(feed_events.c.seq, feed_events.c.change, messages.c.kind, *_MESSAGE_COLUMNS)
                .join(messages, messages.c.id == feed_events.c.message_id)
                .where(feed_events.c.conversation_id == conversation_id, feed_events.c.seq > after)
                .order_by(feed_events.c.seq)
                .limit(FEED_BATCH)
            )
            rows = (await session.execute(statement)).all()
        if not rows or rows[0].seq != after + 1:
            # Начало журнала уже удалено: досылать нечего, клиент перечитает историю.
            return FeedRead((), last, reset=True)
        # Заметки для мастера пропускаем, но позицию двигаем: номера событий без дыр.
        entries = tuple(
            FeedEntry(row.seq, row.change, _view(row)) for row in rows if row.kind not in MASTER_ONLY_KINDS
        )
        return FeedRead(entries, rows[-1].seq)

    @staticmethod
    async def _last_seq(session: AsyncSession, conversation_id: UUID, client_id: UUID) -> int | None:
        statement = select(conversations.c.last_event_seq).where(
            conversations.c.id == conversation_id, conversations.c.client_id == client_id
        )
        last: int | None = (await session.execute(statement)).scalar_one_or_none()
        return last


_SUMMARY_COLUMNS = (
    conversations.c.id,
    conversations.c.client_id,
    conversations.c.client_display_name,
    conversations.c.client_phone_masked,
    conversations.c.completed_visits,
    conversations.c.handler,
    conversations.c.needs_master,
    conversations.c.last_message_author,
    conversations.c.last_message_preview,
    conversations.c.last_message_at,
    conversations.c.unread,
)


def _summary(row: Any) -> ConversationSummaryView:
    last = None
    if row.last_message_at is not None and row.last_message_author is not None:
        last = LastMessageView(
            row.last_message_author.value, row.last_message_preview or "", row.last_message_at
        )
    return ConversationSummaryView(
        id=row.id,
        client_id=row.client_id,
        display_name=row.client_display_name,
        phone_masked=row.client_phone_masked,
        visit_number=row.completed_visits + 1,
        handler=row.handler.value,
        needs_me=None if row.needs_master is None else row.needs_master.value,
        last_message=last,
        unread=row.unread,
    )


def _like(text: str) -> str:
    """Подстрока для ILIKE с экранированием ``%`` и ``_``."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class SqlInboxReader(InboxReader):
    """Чаты мастера: по индексу ``(master_id, last_message_at)``; поиск — по имени,
    цифрам телефона и тексту сообщений."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Получить фабрику сессий."""
        self._session_factory = session_factory

    async def inbox(self, master_id: UUID, filter_by: str, query: str | None) -> InboxView:
        """Список и счётчики."""
        c = conversations.c
        conditions: dict[str, ColumnElement[bool]] = {
            "needs_me": c.needs_master.is_not(None),
            "agent": c.handler == Handler.AGENT,
            "me": c.handler == Handler.MASTER,
        }
        statement = (
            select(*_SUMMARY_COLUMNS)
            .where(c.master_id == master_id)
            .order_by(c.needs_master.is_(None), c.last_message_at.desc().nulls_last(), c.created_at.desc())
            .limit(200)
        )
        if filter_by in conditions:
            statement = statement.where(conditions[filter_by])
        if query:
            statement = statement.where(self._matches(query))
        counts_statement = select(
            func.count().label("all"),
            *(func.count().filter(condition).label(name) for name, condition in conditions.items()),
        ).where(c.master_id == master_id)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
            counts = (await session.execute(counts_statement)).one()
        return InboxView(tuple(_summary(row) for row in rows), dict(counts._mapping))

    async def summary(self, master_id: UUID, conversation_id: UUID) -> ConversationSummaryView | None:
        """Сводка своей переписки."""
        statement = select(*_SUMMARY_COLUMNS).where(
            conversations.c.id == conversation_id, conversations.c.master_id == master_id
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
        return None if row is None else _summary(row)

    async def master_message(self, master_id: UUID, message_id: UUID) -> tuple[UUID, MessageView] | None:
        """Сообщение своего мастера (для кадров потока кабинета)."""
        statement = (
            select(messages.c.conversation_id, *_MESSAGE_COLUMNS)
            .join(conversations, conversations.c.id == messages.c.conversation_id)
            .where(messages.c.id == message_id, conversations.c.master_id == master_id)
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
        return None if row is None else (row.conversation_id, _view(row))

    async def master_page(
        self, conversation_id: UUID, master_id: UUID, before: UUID | None, limit: int
    ) -> MessagePageView | None:
        """История своей переписки."""
        owner = select(conversations.c.id).where(
            conversations.c.id == conversation_id, conversations.c.master_id == master_id
        )
        async with self._session_factory() as session:
            if (await session.execute(owner)).scalar_one_or_none() is None:
                return None
        reader = SqlConversationReader(self._session_factory)
        return await reader.history(conversation_id, before, limit, for_master=True)

    @staticmethod
    def _matches(query: str) -> ColumnElement[bool]:
        c = conversations.c
        pattern = _like(query)
        options: list[ColumnElement[bool]] = [
            c.client_display_name.ilike(pattern, escape="\\"),
            exists().where(
                messages.c.conversation_id == c.id,
                messages.c.content["text"].astext.ilike(pattern, escape="\\"),
            ),
        ]
        digits = re.sub(r"\D", "", query)
        if digits:
            options.append(func.regexp_replace(c.client_phone_masked, r"\D", "", "g").contains(digits))
        return or_(*options)
