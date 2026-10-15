"""Публикация страницы мастера."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.tenancy.application.commands.base import load_master
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class PublishMaster(Command[None]):
    """Открыть страницу клиентам."""

    master_id: UUID


@dataclass(frozen=True, slots=True)
class UnpublishMaster(Command[None]):
    """Скрыть страницу."""

    master_id: UUID


class PublishMasterHandler(Handler[PublishMaster, None]):
    """Публикует страницу (агрегат проверяет готовность)."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: PublishMaster) -> None:
        """Опубликовать."""
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            master.publish(self._clock.now())
            await uow.commit()


class UnpublishMasterHandler(Handler[UnpublishMaster, None]):
    """Снимает страницу с публикации."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: UnpublishMaster) -> None:
        """Скрыть."""
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            master.unpublish(self._clock.now())
            await uow.commit()
