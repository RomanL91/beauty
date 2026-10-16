"""Привязка страницы к учётной записи мастера."""

from __future__ import annotations

from dataclasses import dataclass

from beauty.contexts.tenancy.application.errors import MasterNotFoundError, OwnerTakenError
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.domain.errors import InvalidMasterSlug
from beauty.contexts.tenancy.domain.value_objects import MasterSlug
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class AssignOwner(Command[None]):
    """Мастер входит в кабинет учётной записью с этим телефоном (E.164)."""

    slug: str
    phone: str


class AssignOwnerHandler(Handler[AssignOwner, None]):
    """Один телефон — одна страница."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: AssignOwner) -> None:
        """Привязать."""
        try:
            slug = MasterSlug(message.slug)
        except InvalidMasterSlug as error:
            raise MasterNotFoundError() from error
        async with self._uow as uow:
            master = await uow.masters.get_by_slug(slug)
            if master is None:
                raise MasterNotFoundError()
            other = await uow.masters.get_by_owner(message.phone)
            if other is not None and other.id != master.id:
                raise OwnerTakenError()
            master.assign_owner(message.phone, self._clock.now())
            await uow.commit()
