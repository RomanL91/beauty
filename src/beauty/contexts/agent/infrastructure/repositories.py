"""Репозитории Agent на SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select

from beauty.contexts.agent.domain.office import OfficeMessage
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.repositories import (
    AgentProfileRepository,
    OfficeMessageRepository,
    RunTicketRepository,
)
from beauty.contexts.agent.domain.ticket import RunTicket
from beauty.contexts.agent.infrastructure.tables import office_messages, profiles
from beauty.shared.domain.secrets import HashedSecret
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyAgentProfileRepository(SqlAlchemyRepository[AgentProfile], AgentProfileRepository):
    """Профили агентов."""

    async def get(self, master_id: UUID) -> AgentProfile | None:
        """По мастеру."""
        return self._seen(await self._session.get(AgentProfile, master_id))

    async def by_token(self, token: HashedSecret) -> AgentProfile | None:
        """По дайджесту MCP-токена ресепшна или кабинета (уникальные индексы)."""
        statement = select(AgentProfile).where(
            or_(profiles.c.mcp_token == token, profiles.c.office_mcp_token == token)
        )
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())


class SqlAlchemyRunTicketRepository(SqlAlchemyRepository[RunTicket], RunTicketRepository):
    """Тикеты ходов."""

    async def get(self, ticket_id: str) -> RunTicket | None:
        """По id."""
        return self._seen(await self._session.get(RunTicket, ticket_id))


class SqlAlchemyOfficeMessageRepository(SqlAlchemyRepository[OfficeMessage], OfficeMessageRepository):
    """Лента поручений."""

    async def get(self, master_id: UUID, message_id: UUID) -> OfficeMessage | None:
        """Сообщение своего мастера."""
        message = await self._session.get(OfficeMessage, message_id)
        return self._seen(message if message is not None and message.master_id == master_id else None)

    async def by_client_id(self, master_id: UUID, client_message_id: UUID) -> OfficeMessage | None:
        """По id отправителя (уникальный индекс)."""
        statement = select(OfficeMessage).where(
            office_messages.c.master_id == master_id,
            office_messages.c.client_message_id == client_message_id,
        )
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())

    async def page(
        self, master_id: UUID, before: UUID | None, limit: int
    ) -> tuple[list[OfficeMessage], bool]:
        """UUIDv7 растут со временем: страница — последние ``limit`` до ``before``."""
        statement = select(OfficeMessage).where(office_messages.c.master_id == master_id)
        if before is not None:
            statement = statement.where(office_messages.c.id < before)
        statement = statement.order_by(office_messages.c.id.desc()).limit(limit + 1)
        found = list((await self._session.execute(statement)).scalars())
        return [self._tracker.track(m) for m in reversed(found[:limit])], len(found) > limit
