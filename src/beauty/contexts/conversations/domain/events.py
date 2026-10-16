"""Доменные события Conversations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.shared.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class FeedAppended(DomainEvent):
    """В ленте переписки появилось или изменилось сообщение.

    ``seq`` — номер события ленты (растёт без пропусков в пределах переписки); он же
    ``id`` кадра SSE для ``Last-Event-ID``. Событие пишется в журнал ленты и будит
    открытые потоки через realtime-мост.
    """

    routing_key = "conversations.feed.appended"

    conversation_id: UUID
    master_id: UUID
    seq: int
    change: str
    message_id: UUID


@dataclass(frozen=True, kw_only=True)
class ClientMessagePosted(DomainEvent):
    """Клиент написал: текст, голосовое или намерение записаться.

    Подписчик — администратор записи (сейчас — обработчик намерений, позже — агент).
    """

    routing_key = "conversations.client.message_posted"

    conversation_id: UUID
    message_id: UUID
    master_id: UUID
    client_id: UUID
    intent: str
    text: str | None = None
    service_id: UUID | None = None
    start: datetime | None = None
    offer_id: UUID | None = None


@dataclass(frozen=True, kw_only=True)
class ConversationChanged(DomainEvent):
    """Изменилась сводка переписки для мастера (обработчик, «нужны вы», счётчики)."""

    routing_key = "conversations.conversation.changed"

    conversation_id: UUID
    master_id: UUID


@dataclass(frozen=True, kw_only=True)
class MessageAdded(DomainEvent):
    """В переписке новое сообщение: кто, какого вида, превью и кто сейчас ведёт диалог.

    Для тех, кому важно «кто кому написал» (уведомления), без чтения ленты.
    """

    routing_key = "conversations.message.added"

    conversation_id: UUID
    master_id: UUID
    client_id: UUID
    message_id: UUID
    author: str
    kind: str
    preview: str
    handler: str
