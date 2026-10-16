"""Репозитории Conversations на SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from beauty.contexts.conversations.domain.conversation import Conversation
from beauty.contexts.conversations.domain.message import Message
from beauty.contexts.conversations.domain.repositories import ConversationRepository, MessageRepository
from beauty.contexts.conversations.infrastructure.tables import conversations, messages
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyConversationRepository(SqlAlchemyRepository[Conversation], ConversationRepository):
    """Переписки — с блокировкой строки (``FOR UPDATE``).

    Переписку загружают только для того, чтобы записать событие ленты; блокировка
    выстраивает такие транзакции одной переписки в очередь, и номер события растёт в
    порядке коммитов без повторов. Оптимистичная версия остаётся страховкой.
    """

    async def get(self, conversation_id: UUID) -> Conversation | None:
        """По первичному ключу."""
        return self._seen(await self._session.get(Conversation, conversation_id, with_for_update=True))

    async def find(self, master_id: UUID, client_id: UUID) -> Conversation | None:
        """По уникальной паре."""
        statement = (
            select(Conversation)
            .where(conversations.c.master_id == master_id, conversations.c.client_id == client_id)
            .with_for_update()
        )
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())


class SqlAlchemyMessageRepository(SqlAlchemyRepository[Message], MessageRepository):
    """Сообщения."""

    async def get(self, message_id: UUID) -> Message | None:
        """По первичному ключу."""
        return self._seen(await self._session.get(Message, message_id))

    async def by_client_id(self, conversation_id: UUID, client_message_id: UUID) -> Message | None:
        """По ключу идемпотентности (уникальный частичный индекс)."""
        statement = select(Message).where(
            messages.c.conversation_id == conversation_id, messages.c.client_message_id == client_message_id
        )
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())

    async def card_of(self, conversation_id: UUID, appointment_id: UUID) -> Message | None:
        """Карточка заявки (уникальный частичный индекс)."""
        statement = select(Message).where(
            messages.c.conversation_id == conversation_id, messages.c.appointment_id == appointment_id
        )
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())
