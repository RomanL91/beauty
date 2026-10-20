"""Услуги мастера."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.tenancy.application.commands.base import as_service_not_found, load_master
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.domain.errors import UnknownService
from beauty.contexts.tenancy.domain.value_objects import Money, ServiceDuration
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class AddService(Command[UUID]):
    """Добавить услугу. ``price_amount`` — в тиынах, ``None`` — «цена по запросу»."""

    master_id: UUID
    title: str
    duration_min: int
    price_amount: int | None
    description: str = ""


class AddServiceHandler(Handler[AddService, UUID]):
    """Добавляет услугу в агрегат."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: AddService) -> UUID:
        """Добавить и вернуть id услуги."""
        duration = ServiceDuration(message.duration_min)
        price = None if message.price_amount is None else Money(message.price_amount)
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            service = master.add_service(
                self._ids.new(), message.title, duration, price, self._clock.now(), message.description
            )
            await uow.commit()
            return service.id


@dataclass(frozen=True, slots=True)
class UpdateService(Command[None]):
    """Изменить услугу."""

    master_id: UUID
    service_id: UUID
    title: str
    duration_min: int
    price_amount: int | None
    description: str = ""


class UpdateServiceHandler(Handler[UpdateService, None]):
    """Изменяет услугу в агрегате."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: UpdateService) -> None:
        """Применить изменения."""
        duration = ServiceDuration(message.duration_min)
        price = None if message.price_amount is None else Money(message.price_amount)
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            try:
                master.update_service(
                    message.service_id, message.title, duration, price, self._clock.now(), message.description
                )
            except UnknownService as error:
                raise as_service_not_found(error) from error
            await uow.commit()


@dataclass(frozen=True, slots=True)
class ArchiveService(Command[None]):
    """Убрать услугу из записи."""

    master_id: UUID
    service_id: UUID


class ArchiveServiceHandler(Handler[ArchiveService, None]):
    """Архивирует услугу."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: ArchiveService) -> None:
        """Архивировать."""
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            try:
                master.archive_service(message.service_id, self._clock.now())
            except UnknownService as error:
                raise as_service_not_found(error) from error
            await uow.commit()
