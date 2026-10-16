"""Unit of Work контекста Tenancy."""

from __future__ import annotations

from beauty.contexts.tenancy.domain.repositories import MasterRepository
from beauty.shared.application.uow import UnitOfWork


class TenancyUnitOfWork(UnitOfWork):
    """Unit of Work с репозиторием мастеров."""

    masters: MasterRepository
