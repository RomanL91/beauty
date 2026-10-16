"""Агрегат ``Conversation`` — переписка клиента с администратором мастера.

Сообщения — отдельные агрегаты (история неограниченна), а переписка держит счётчик
событий ленты. Каждое новое или изменённое сообщение получает номер через
``record``: счётчик растёт под блокировкой строки переписки, поэтому номера в пределах
переписки идут без пропусков в порядке коммитов — клиент, продолжающий поток с
``Last-Event-ID``, ничего не пропустит.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from beauty.contexts.conversations.domain.events import FeedAppended
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.domain.aggregate import AggregateRoot


class FeedChange(StrEnum):
    """Что произошло с сообщением ленты."""

    CREATED = "message.created"
    UPDATED = "message.updated"


class Conversation(AggregateRoot):
    """Переписка клиента с мастером (одна на пару)."""

    def __init__(self, conversation_id: UUID, master_id: UUID, client_id: UUID, created_at: datetime) -> None:
        """Создать переписку (используйте ``open``)."""
        self.id = conversation_id
        self.master_id = master_id
        self.client_id = client_id
        self.last_event_seq = 0
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def open(cls, *, conversation_id: UUID, master_id: UUID, client_id: UUID, now: datetime) -> Conversation:
        """Начать переписку."""
        return cls(conversation_id, master_id, client_id, now)

    def record(self, message: Message, change: FeedChange, now: datetime) -> int:
        """Зафиксировать событие ленты и вернуть его номер."""
        if message.conversation_id != self.id:
            raise ValueError("Сообщение из другой переписки")
        self.last_event_seq += 1
        self.updated_at = now
        self._record(
            FeedAppended(
                occurred_at=now,
                conversation_id=self.id,
                seq=self.last_event_seq,
                change=change.value,
                message_id=message.id,
            )
        )
        return self.last_event_seq
