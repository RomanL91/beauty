"""Порты репозиториев Agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.ticket import RunTicket
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
        """Профиль по MCP-токену."""


class RunTicketRepository(ABC):
    """Тикеты ходов."""

    @abstractmethod
    def add(self, ticket: RunTicket) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, ticket_id: str) -> RunTicket | None:
        """Тикет по id."""
