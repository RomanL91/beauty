"""Репозитории Agent на SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.repositories import AgentProfileRepository, RunTicketRepository
from beauty.contexts.agent.domain.ticket import RunTicket
from beauty.contexts.agent.infrastructure.tables import profiles
from beauty.shared.domain.secrets import HashedSecret
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyAgentProfileRepository(SqlAlchemyRepository[AgentProfile], AgentProfileRepository):
    """Профили агентов."""

    async def get(self, master_id: UUID) -> AgentProfile | None:
        """По мастеру."""
        return self._seen(await self._session.get(AgentProfile, master_id))

    async def by_token(self, token: HashedSecret) -> AgentProfile | None:
        """По дайджесту MCP-токена (уникальный индекс)."""
        statement = select(AgentProfile).where(profiles.c.mcp_token == token)
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())


class SqlAlchemyRunTicketRepository(SqlAlchemyRepository[RunTicket], RunTicketRepository):
    """Тикеты ходов."""

    async def get(self, ticket_id: str) -> RunTicket | None:
        """По id."""
        return self._seen(await self._session.get(RunTicket, ticket_id))
