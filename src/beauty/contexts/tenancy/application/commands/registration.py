"""Регистрация мастера."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.tenancy.application.errors import SlugTakenError
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.domain.master import Master
from beauty.contexts.tenancy.domain.value_objects import MasterSlug, NameForms, TimeZoneName
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class RegisterMaster(Command[UUID]):
    """Зарегистрировать мастера (страница — черновик)."""

    slug: str
    display_name: str
    name_nominative: str
    name_genitive: str
    name_dative: str
    timezone: str = "Asia/Almaty"


class RegisterMasterHandler(Handler[RegisterMaster, UUID]):
    """Создаёт агрегат ``Master``.

    Проверка «slug свободен» — быстрый путь; гонку двух регистраций одного slug
    закрывает уникальный индекс: нарушение → ``ConcurrencyConflictError`` → повтор
    медиатором → на повторе проверка увидит занятый slug.
    """

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: RegisterMaster) -> UUID:
        """Зарегистрировать и вернуть id."""
        slug = MasterSlug(message.slug)
        async with self._uow as uow:
            if await uow.masters.get_by_slug(slug) is not None:
                raise SlugTakenError(f"Адрес {slug.value} уже занят")
            master = Master.register(
                master_id=self._ids.new(),
                slug=slug,
                display_name=message.display_name,
                name_forms=NameForms(message.name_nominative, message.name_genitive, message.name_dative),
                timezone=TimeZoneName(message.timezone),
                now=self._clock.now(),
            )
            uow.masters.add(master)
            await uow.commit()
            return master.id
