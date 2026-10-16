"""Unit of Work Conversations: журнал ленты пишется в той же транзакции."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.events import FeedAppended
from beauty.contexts.conversations.infrastructure.repositories import (
    SqlAlchemyConversationRepository,
    SqlAlchemyMessageRepository,
)
from beauty.contexts.conversations.infrastructure.tables import feed_events
from beauty.shared.domain.events import DomainEvent
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyConversationsUnitOfWork(SqlAlchemyUnitOfWork, ConversationsUnitOfWork):
    """Переписки и сообщения; события ``FeedAppended`` дублируются в журнал ленты."""

    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Инициализировать репозитории."""
        self.conversations = SqlAlchemyConversationRepository(session, tracker)
        self.messages = SqlAlchemyMessageRepository(session, tracker)

    async def _before_outbox(self, session: AsyncSession, events: Sequence[DomainEvent]) -> None:
        """Записать события ленты в журнал (для досылки по ``Last-Event-ID``)."""
        rows = [
            {
                "conversation_id": event.conversation_id,
                "seq": event.seq,
                "change": event.change,
                "message_id": event.message_id,
                "created_at": event.occurred_at,
            }
            for event in events
            if isinstance(event, FeedAppended)
        ]
        if rows:
            await session.execute(insert(feed_events), rows)
