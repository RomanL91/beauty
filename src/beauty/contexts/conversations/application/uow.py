"""Unit of Work контекста Conversations."""

from __future__ import annotations

from beauty.contexts.conversations.domain.repositories import (
    BroadcastRepository,
    ConversationRepository,
    MessageRepository,
)
from beauty.shared.application.uow import UnitOfWork


class ConversationsUnitOfWork(UnitOfWork):
    """Переписки и сообщения в одной транзакции."""

    conversations: ConversationRepository
    messages: MessageRepository
    broadcasts: BroadcastRepository
