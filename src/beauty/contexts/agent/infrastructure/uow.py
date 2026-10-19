"""Unit of Work Agent на SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from beauty.contexts.agent.application.uow import AgentUnitOfWork
from beauty.contexts.agent.infrastructure.repositories import (
    SqlAlchemyAgentProfileRepository,
    SqlAlchemyAgentRunRepository,
    SqlAlchemyOfficeMessageRepository,
    SqlAlchemyRunTicketRepository,
)
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyAgentUnitOfWork(SqlAlchemyUnitOfWork, AgentUnitOfWork):
    """Профили, тикеты и лента поручений поверх сессии единицы работы."""

    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Инициализировать репозитории."""
        self.profiles = SqlAlchemyAgentProfileRepository(session, tracker)
        self.tickets = SqlAlchemyRunTicketRepository(session, tracker)
        self.office = SqlAlchemyOfficeMessageRepository(session, tracker)
        self.runs = SqlAlchemyAgentRunRepository(session, tracker)
