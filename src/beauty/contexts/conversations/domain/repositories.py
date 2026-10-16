"""Порты репозиториев Conversations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from beauty.contexts.conversations.domain.conversation import Conversation
from beauty.contexts.conversations.domain.message import Message


class ConversationRepository(ABC):
    """Переписки."""

    @abstractmethod
    def add(self, conversation: Conversation) -> None:
        """Добавить новую."""

    @abstractmethod
    async def get(self, conversation_id: UUID) -> Conversation | None:
        """По id."""

    @abstractmethod
    async def find(self, master_id: UUID, client_id: UUID) -> Conversation | None:
        """Переписка клиента с мастером."""


class MessageRepository(ABC):
    """Сообщения."""

    @abstractmethod
    def add(self, message: Message) -> None:
        """Добавить новое."""

    @abstractmethod
    async def get(self, message_id: UUID) -> Message | None:
        """По id."""

    @abstractmethod
    async def by_client_id(self, conversation_id: UUID, client_message_id: UUID) -> Message | None:
        """Сообщение, отправленное с этим ``client_id`` (идемпотентность)."""

    @abstractmethod
    async def card_of(self, conversation_id: UUID, appointment_id: UUID) -> Message | None:
        """Карточка заявки в переписке."""
