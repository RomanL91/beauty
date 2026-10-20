"""Порты репозиториев Conversations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from beauty.contexts.conversations.domain.broadcast import Broadcast
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

    @abstractmethod
    async def batch_of_master(
        self, master_id: UUID, after: UUID | None, opened_before: datetime, limit: int
    ) -> list[Conversation]:
        """Порция переписок мастера по возрастанию id (для рассылки), открытых до момента."""

    @abstractmethod
    async def count_of_master(self, master_id: UUID) -> int:
        """Сколько у мастера переписок (получателей рассылки)."""


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


class BroadcastRepository(ABC):
    """Рассылки и запрет рассылок мастеру."""

    @abstractmethod
    def add(self, broadcast: Broadcast) -> None:
        """Добавить черновик."""

    @abstractmethod
    async def get(self, broadcast_id: UUID) -> Broadcast | None:
        """По id."""

    @abstractmethod
    async def remove(self, broadcast: Broadcast) -> None:
        """Удалить черновик."""

    @abstractmethod
    async def last_started(self, master_id: UUID) -> datetime | None:
        """Когда мастер последний раз отправлял рассылку."""

    @abstractmethod
    async def blocked(self, master_id: UUID) -> bool:
        """Запрещены ли мастеру рассылки."""

    @abstractmethod
    async def set_blocked(self, master_id: UUID, blocked: bool, now: datetime) -> None:
        """Запретить или разрешить рассылки."""
