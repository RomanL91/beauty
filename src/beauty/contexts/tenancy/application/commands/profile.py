"""Профиль страницы мастера и фото работ."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.tenancy.application.commands.base import load_master
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.domain.master import MasterProfile
from beauty.contexts.tenancy.domain.value_objects import NameForms, PortfolioPhoto, TimeZoneName
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class UpdateMasterProfile(Command[None]):
    """Обновить профиль страницы."""

    master_id: UUID
    display_name: str
    name_nominative: str
    name_genitive: str
    name_dative: str
    specialty: str
    address: str
    about: str
    timezone: str
    avatar_url: str | None = None


class UpdateMasterProfileHandler(Handler[UpdateMasterProfile, None]):
    """Обновляет профиль через агрегат."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: UpdateMasterProfile) -> None:
        """Применить профиль."""
        profile = MasterProfile(
            display_name=message.display_name,
            name_forms=NameForms(message.name_nominative, message.name_genitive, message.name_dative),
            specialty=message.specialty,
            address=message.address,
            about=message.about,
            timezone=TimeZoneName(message.timezone),
            avatar_url=message.avatar_url,
        )
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            master.update_profile(profile, self._clock.now())
            await uow.commit()


@dataclass(frozen=True, slots=True)
class ReplacePortfolio(Command[None]):
    """Заменить фото работ: ``(id, https-url, подпись)``."""

    master_id: UUID
    photos: tuple[tuple[UUID, str, str], ...]


class ReplacePortfolioHandler(Handler[ReplacePortfolio, None]):
    """Заменяет подборку фото."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: ReplacePortfolio) -> None:
        """Сохранить подборку."""
        photos = [PortfolioPhoto(photo_id, url, alt) for photo_id, url, alt in message.photos]
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            master.replace_photos(photos, self._clock.now())
            await uow.commit()
