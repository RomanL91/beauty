"""Unit of Work контекста Admin."""

from __future__ import annotations

from beauty.contexts.admin.domain.repositories import (
    AdministratorRepository,
    AdminSessionRepository,
    AuditRepository,
)
from beauty.shared.application.uow import UnitOfWork


class AdminUnitOfWork(UnitOfWork):
    """Администраторы, сессии и журнал действий."""

    admins: AdministratorRepository
    sessions: AdminSessionRepository
    audit: AuditRepository
