"""Порты репозиториев Agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from beauty.contexts.agent.domain.office import OfficeMessage
from beauty.contexts.agent.domain.playbook import Playbook
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.run import AgentRun
from beauty.contexts.agent.domain.ticket import AgentFace, RunTicket
from beauty.shared.domain.secrets import HashedSecret


class AgentProfileRepository(ABC):
    """Профили агентов."""

    @abstractmethod
    def add(self, profile: AgentProfile) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, master_id: UUID) -> AgentProfile | None:
        """Профиль мастера."""

    @abstractmethod
    async def by_token(self, token: HashedSecret) -> AgentProfile | None:
        """Профиль по MCP-токену ресепшна или кабинета."""


class RunTicketRepository(ABC):
    """Тикеты ходов."""

    @abstractmethod
    def add(self, ticket: RunTicket) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, ticket_id: str) -> RunTicket | None:
        """Тикет по id."""

    @abstractmethod
    async def latest(
        self, master_id: UUID, face: AgentFace, conversation_id: UUID | None
    ) -> RunTicket | None:
        """Последний тикет нити: переписки ресепшна или (``None``) кабинета мастера."""


class OfficeMessageRepository(ABC):
    """Лента поручений."""

    @abstractmethod
    def add(self, message: OfficeMessage) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, master_id: UUID, message_id: UUID) -> OfficeMessage | None:
        """Сообщение ленты мастера (чужое — ``None``)."""

    @abstractmethod
    async def by_client_id(self, master_id: UUID, client_message_id: UUID) -> OfficeMessage | None:
        """Поручение по id отправителя (повтор отправки)."""

    @abstractmethod
    async def page(
        self, master_id: UUID, before: UUID | None, limit: int
    ) -> tuple[list[OfficeMessage], bool]:
        """Страница ленты по возрастанию времени и признак «есть раньше»."""


class AgentRunRepository(ABC):
    """Журнал ходов."""

    @abstractmethod
    def add(self, run: AgentRun) -> None:
        """Записать ход."""


class PlaybookRepository(ABC):
    """Опыт мастеров."""

    @abstractmethod
    def add(self, playbook: Playbook) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, master_id: UUID) -> Playbook | None:
        """Опыт мастера (ещё не заведён — ``None``)."""
