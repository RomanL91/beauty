"""Unit of Work контекста Agent."""

from __future__ import annotations

from beauty.contexts.agent.domain.repositories import AgentProfileRepository, RunTicketRepository
from beauty.shared.application.uow import UnitOfWork


class AgentUnitOfWork(UnitOfWork):
    """Профили и тикеты."""

    profiles: AgentProfileRepository
    tickets: RunTicketRepository
