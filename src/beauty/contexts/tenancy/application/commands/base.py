"""Общая часть обработчиков команд Tenancy."""

from __future__ import annotations

from uuid import UUID

from beauty.contexts.tenancy.application.errors import MasterNotFoundError, ServiceNotFoundError
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.domain.errors import UnknownService
from beauty.contexts.tenancy.domain.master import Master


async def load_master(uow: TenancyUnitOfWork, master_id: UUID) -> Master:
    """Мастер по id или ``MasterNotFoundError``."""
    master = await uow.masters.get(master_id)
    if master is None:
        raise MasterNotFoundError()
    return master


def as_service_not_found(error: UnknownService) -> ServiceNotFoundError:
    """Доменное «нет услуги» → прикладное «не найдено» (404)."""
    return ServiceNotFoundError(str(error))
