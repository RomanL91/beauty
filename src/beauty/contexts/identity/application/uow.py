"""Unit of Work контекста Identity."""

from __future__ import annotations

from beauty.contexts.identity.domain.repositories import (
    AuthChallengeRepository,
    ClientAccountRepository,
    ClientSessionRepository,
)
from beauty.shared.application.uow import UnitOfWork


class IdentityUnitOfWork(UnitOfWork):
    """Unit of Work с репозиториями Identity."""

    challenges: AuthChallengeRepository
    accounts: ClientAccountRepository
    sessions: ClientSessionRepository
