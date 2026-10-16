"""Настройки страницы мастера (кабинет владельца)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.tenancy.application.commands.base import load_master
from beauty.contexts.tenancy.application.dto import MasterPageView, MasterSettingsView, PhotoView, ServiceView
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.domain.master import Master
from beauty.shared.application.cqrs import Handler, Query


@dataclass(frozen=True, slots=True)
class GetMasterSettings(Query[MasterSettingsView]):
    """Настройки своей страницы (и черновика)."""

    master_id: UUID


class GetMasterSettingsHandler(Handler[GetMasterSettings, MasterSettingsView]):
    """Читает агрегат: настройки — это всё, что мастер может поменять."""

    def __init__(self, uow: TenancyUnitOfWork) -> None:
        """Получить Unit of Work."""
        self._uow = uow

    async def handle(self, message: GetMasterSettings) -> MasterSettingsView:
        """Собрать настройки."""
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            return settings_of(master)


def settings_of(master: Master) -> MasterSettingsView:
    """Настройки из агрегата."""
    rules = master.booking_rules
    page = MasterPageView(
        id=master.id,
        slug=master.slug.value,
        display_name=master.display_name,
        name_nominative=master.name_forms.nominative,
        name_genitive=master.name_forms.genitive,
        name_dative=master.name_forms.dative,
        specialty=master.specialty,
        address=master.address,
        timezone=master.timezone.value,
        avatar_url=master.avatar_url,
        about=master.about,
        services=tuple(
            ServiceView(s.id, s.title, s.duration.minutes, None if s.price is None else s.price.amount)
            for s in master.active_services
        ),
        photos=tuple(PhotoView(p.id, p.url, p.alt) for p in master.photos),
        confirm_within_hours=rules.confirm_within_hours,
        change_deadline_hours=rules.change_deadline_hours,
    )
    return MasterSettingsView(
        page=page,
        published=master.is_published,
        published_at=master.published_at,
        working_hours=tuple(
            (weekday, tuple((h.start, h.end) for h in master.schedule.hours_on(weekday)))
            for weekday in range(7)
            if master.schedule.hours_on(weekday)
        ),
        days_off=master.days_off,
        min_notice_minutes=rules.min_notice_minutes,
        horizon_days=rules.horizon_days,
        slot_step_minutes=rules.slot_step_minutes,
        publish_blockers=master.publish_blockers,
    )
