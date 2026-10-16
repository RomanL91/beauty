"""Unit of Work контекста Agent."""

from __future__ import annotations

from beauty.contexts.agent.domain.repositories import (
    AgentProfileRepository,
    OfficeMessageRepository,
    RunTicketRepository,
)
from beauty.shared.application.uow import UnitOfWork


class AgentUnitOfWork(UnitOfWork):
    """Профили, тикеты и лента поручений."""

    profiles: AgentProfileRepository
    tickets: RunTicketRepository
    office: OfficeMessageRepository
