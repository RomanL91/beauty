"""Репозитории Conversations на SQLAlchemy."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from beauty.contexts.conversations.domain.broadcast import Broadcast
from beauty.contexts.conversations.domain.conversation import Conversation
from beauty.contexts.conversations.domain.message import Message
from beauty.contexts.conversations.domain.repositories import (
    BroadcastRepository,
    ConversationRepository,
    MessageRepository,
)
from beauty.contexts.conversations.infrastructure.tables import (
    broadcast_blocks,
    broadcasts,
    conversations,
    messages,
)
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

    async def batch_of_master(
        self, master_id: UUID, after: UUID | None, opened_before: datetime, limit: int
    ) -> list[Conversation]:
        """Порция по возрастанию id; строки блокируются, как и при записи в ленту."""
        statement = (
            select(Conversation)
            .where(conversations.c.master_id == master_id, conversations.c.created_at <= opened_before)
            .order_by(conversations.c.id)
            .limit(limit)
            .with_for_update()
        )
        if after is not None:
            statement = statement.where(conversations.c.id > after)
        found = (await self._session.execute(statement)).scalars().all()
        return [self._tracker.track(conversation) for conversation in found]

    async def count_of_master(self, master_id: UUID) -> int:
        """Число переписок мастера."""
        statement = select(func.count()).where(conversations.c.master_id == master_id)
        return int((await self._session.execute(statement)).scalar_one())


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


class SqlAlchemyBroadcastRepository(SqlAlchemyRepository[Broadcast], BroadcastRepository):
    """Рассылки; запрет рассылок — отдельная строка на мастера."""

    async def get(self, broadcast_id: UUID) -> Broadcast | None:
        """По первичному ключу (с блокировкой: отправка и доставка не идут параллельно)."""
        return self._seen(await self._session.get(Broadcast, broadcast_id, with_for_update=True))

    async def remove(self, broadcast: Broadcast) -> None:
        """Удалить черновик."""
        await self._session.delete(broadcast)

    async def last_started(self, master_id: UUID) -> datetime | None:
        """Последнее начало отправки."""
        statement = select(func.max(broadcasts.c.started_at)).where(broadcasts.c.master_id == master_id)
        found: datetime | None = (await self._session.execute(statement)).scalar_one()
        return found

    async def blocked(self, master_id: UUID) -> bool:
        """Есть ли запрет."""
        statement = select(broadcast_blocks.c.master_id).where(broadcast_blocks.c.master_id == master_id)
        return (await self._session.execute(statement)).first() is not None

    async def set_blocked(self, master_id: UUID, blocked: bool, now: datetime) -> None:
        """Поставить или снять запрет (идемпотентно)."""
        if blocked:
            await self._session.execute(
                insert(broadcast_blocks).values(master_id=master_id, blocked_at=now).on_conflict_do_nothing()
            )
        else:
            await self._session.execute(
                delete(broadcast_blocks).where(broadcast_blocks.c.master_id == master_id)
            )
