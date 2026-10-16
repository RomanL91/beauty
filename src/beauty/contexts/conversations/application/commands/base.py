"""Общая часть обработчиков команд Conversations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from beauty.contexts.conversations.application.errors import ConversationNotFoundError
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.conversation import Conversation, FeedChange
from beauty.contexts.conversations.domain.message import Message


async def load_conversation(
    uow: ConversationsUnitOfWork,
    conversation_id: UUID,
    client_id: UUID | None = None,
    master_id: UUID | None = None,
) -> Conversation:
    """Переписка по id; с ``client_id``/``master_id`` — только своя."""
    conversation = await uow.conversations.get(conversation_id)
    if (
        conversation is None
        or (client_id is not None and conversation.client_id != client_id)
        or (master_id is not None and conversation.master_id != master_id)
    ):
        raise ConversationNotFoundError()
    return conversation


def post(uow: ConversationsUnitOfWork, conversation: Conversation, message: Message, now: datetime) -> None:
    """Добавить сообщение в ленту."""
    uow.messages.add(message)
    conversation.record(message, FeedChange.CREATED, now)


def revise(conversation: Conversation, message: Message, now: datetime) -> None:
    """Отметить изменение сообщения в ленте."""
    conversation.record(message, FeedChange.UPDATED, now)
