"""DTO Conversations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.contexts.conversations.domain.content import Author, MessageContent
from beauty.contexts.conversations.domain.message import Message


@dataclass(frozen=True, slots=True)
class ConversationView:
    """Переписка клиента."""

    id: UUID
    master_id: UUID


@dataclass(frozen=True, slots=True)
class ConversationState:
    """Переписка для агента: чья, с кем и кто ведёт."""

    id: UUID
    master_id: UUID
    client_id: UUID
    client_name: str
    handler: str


@dataclass(frozen=True, slots=True)
class OpenedConversation:
    """Результат открытия переписки."""

    id: UUID
    master_slug: str
    created: bool


@dataclass(frozen=True, slots=True)
class MessageView:
    """Сообщение для API."""

    id: UUID
    client_message_id: UUID | None
    author: Author
    ai_generated: bool
    created_at: datetime
    content: MessageContent

    @classmethod
    def of(cls, message: Message) -> MessageView:
        """Из агрегата."""
        return cls(
            message.id,
            message.client_message_id,
            message.author,
            message.ai_generated,
            message.created_at,
            message.content,
        )


@dataclass(frozen=True, slots=True)
class MessagePageView:
    """Страница истории по возрастанию времени."""

    items: tuple[MessageView, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class FeedEntry:
    """Событие ленты: номер, вид изменения и текущее состояние сообщения."""

    seq: int
    change: str
    message: MessageView


@dataclass(frozen=True, slots=True)
class FeedRead:
    """Результат чтения ленты.

    ``reset`` — запрошенная позиция старше журнала (или из будущего): клиенту нужно
    перечитать историю; ``last_seq`` — с какой позиции продолжать.
    """

    entries: tuple[FeedEntry, ...]
    last_seq: int
    reset: bool = False


@dataclass(frozen=True, slots=True)
class LastMessageView:
    """Последнее сообщение в списке чатов."""

    author: str
    preview: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationSummaryView:
    """Чат в списке мастера."""

    id: UUID
    client_id: UUID
    display_name: str
    phone_masked: str
    visit_number: int
    handler: str
    needs_me: str | None
    last_message: LastMessageView | None
    unread: int


@dataclass(frozen=True, slots=True)
class InboxView:
    """Список чатов и счётчики фильтров."""

    items: tuple[ConversationSummaryView, ...]
    counts: dict[str, int]
