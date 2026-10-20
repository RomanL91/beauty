"""Модуль контекста Tenancy: сборка зависимостей и регистрация в приложении."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.tenancy.application.commands import (
    AddPortfolioPhoto,
    AddPortfolioPhotoHandler,
    AddService,
    AddServiceHandler,
    ArchiveService,
    ArchiveServiceHandler,
    AssignOwner,
    AssignOwnerHandler,
    ChangeDayOff,
    ChangeDayOffHandler,
    PublishMaster,
    PublishMasterHandler,
    RegisterMaster,
    RegisterMasterHandler,
    RemovePortfolioPhoto,
    RemovePortfolioPhotoHandler,
    ReplacePortfolio,
    ReplacePortfolioHandler,
    SetAvatar,
    SetAvatarHandler,
    SetBookingRules,
    SetBookingRulesHandler,
    SetDaysOff,
    SetDaysOffHandler,
    SetWeeklySchedule,
    SetWeeklyScheduleHandler,
    UnpublishMaster,
    UnpublishMasterHandler,
    UpdateMasterProfile,
    UpdateMasterProfileHandler,
    UpdateService,
    UpdateServiceHandler,
)
from beauty.contexts.tenancy.application.ports import BusyTimeSource
from beauty.contexts.tenancy.application.queries import (
    CheckBookableSlot,
    CheckBookableSlotHandler,
    FindMasterByOwner,
    FindMasterByOwnerHandler,
    FindMasterId,
    FindMasterIdHandler,
    GetMasterPage,
    GetMasterPageHandler,
    GetMasterSettings,
    GetMasterSettingsHandler,
    GetWorkingCalendar,
    GetWorkingCalendarHandler,
    ListFreeSlots,
    ListFreeSlotsHandler,
    ListRemovedServices,
    ListRemovedServicesHandler,
    ListServiceTitles,
    ListServiceTitlesHandler,
)
from beauty.contexts.tenancy.domain.slots import SlotFinder
from beauty.contexts.tenancy.infrastructure.busy import NoBusyTime
from beauty.contexts.tenancy.infrastructure.mapping import TenancyOrmMapper
from beauty.contexts.tenancy.infrastructure.readers import (
    SqlAvailabilityReader,
    SqlMasterDirectory,
    SqlMasterPageReader,
)
from beauty.contexts.tenancy.infrastructure.uow import SqlAlchemyTenancyUnitOfWork
from beauty.contexts.tenancy.presentation.api.cabinet import cabinet_router
from beauty.contexts.tenancy.presentation.api.controller import TenancyApiController
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.storage import FileStorage
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.web.auth import MasterAuth
from beauty.shared.infrastructure.web.errors import HttpErrorMapper

_HTTP_STATUSES: dict[str, int] = {
    "master_not_found": 404,
    "service_not_found": 404,
    "slug_taken": 409,
    "owner_taken": 409,
    "master_not_publishable": 409,
    "service_limit_reached": 409,
    "slot_unavailable": 409,
    "invalid_slot_window": 422,
    "invalid_slug": 422,
    "invalid_profile": 422,
    "invalid_timezone": 422,
    "invalid_service_duration": 422,
    "invalid_money": 422,
    "invalid_booking_rules": 422,
    "invalid_schedule": 422,
    "photo_not_found": 404,
    "invalid_photo": 422,
    "photo_too_large": 413,
}


@dataclass(frozen=True, slots=True)
class TenancyDependencies:
    """Общие зависимости от корня композиции.

    ``busy_time`` — источник занятого времени; до контекста записи — пустой.
    """

    session_factory: async_sessionmaker[AsyncSession]
    outbox_writer: OutboxWriter
    clock: Clock
    id_generator: IdGenerator
    busy_time: BusyTimeSource | None = None


class TenancyModule:
    """Сборка контекста Tenancy."""

    def __init__(self, dependencies: TenancyDependencies) -> None:
        """Создать долгоживущие (stateless) компоненты контекста."""
        TenancyOrmMapper.map()
        self._deps = dependencies
        self._page_reader = SqlMasterPageReader(dependencies.session_factory)
        self._availability_reader = SqlAvailabilityReader(dependencies.session_factory)
        self._directory = SqlMasterDirectory(dependencies.session_factory)
        self._busy = dependencies.busy_time or NoBusyTime()
        self._finder = SlotFinder()

    def register(self, mediator: Mediator, http_errors: HttpErrorMapper) -> None:
        """Зарегистрировать обработчики и коды ошибок."""
        deps = self._deps
        clock, ids = deps.clock, deps.id_generator
        mediator.register(RegisterMaster, lambda: RegisterMasterHandler(self._uow(), clock, ids))
        mediator.register(UpdateMasterProfile, lambda: UpdateMasterProfileHandler(self._uow(), clock))
        mediator.register(ReplacePortfolio, lambda: ReplacePortfolioHandler(self._uow(), clock))
        mediator.register(AddService, lambda: AddServiceHandler(self._uow(), clock, ids))
        mediator.register(UpdateService, lambda: UpdateServiceHandler(self._uow(), clock))
        mediator.register(ArchiveService, lambda: ArchiveServiceHandler(self._uow(), clock))
        mediator.register(SetWeeklySchedule, lambda: SetWeeklyScheduleHandler(self._uow(), clock))
        mediator.register(SetBookingRules, lambda: SetBookingRulesHandler(self._uow(), clock))
        mediator.register(SetDaysOff, lambda: SetDaysOffHandler(self._uow(), clock))
        mediator.register(ChangeDayOff, lambda: ChangeDayOffHandler(self._uow(), clock))
        mediator.register(AddPortfolioPhoto, lambda: AddPortfolioPhotoHandler(self._uow(), clock))
        mediator.register(RemovePortfolioPhoto, lambda: RemovePortfolioPhotoHandler(self._uow(), clock))
        mediator.register(SetAvatar, lambda: SetAvatarHandler(self._uow(), clock))
        mediator.register(GetMasterSettings, lambda: GetMasterSettingsHandler(self._uow()))
        mediator.register(PublishMaster, lambda: PublishMasterHandler(self._uow(), clock))
        mediator.register(UnpublishMaster, lambda: UnpublishMasterHandler(self._uow(), clock))
        mediator.register(GetMasterPage, lambda: GetMasterPageHandler(self._page_reader))
        mediator.register(FindMasterId, lambda: FindMasterIdHandler(self._directory))
        mediator.register(FindMasterByOwner, lambda: FindMasterByOwnerHandler(self._directory))
        mediator.register(GetWorkingCalendar, lambda: GetWorkingCalendarHandler(self._availability_reader))
        mediator.register(AssignOwner, lambda: AssignOwnerHandler(self._uow(), clock))
        mediator.register(ListServiceTitles, lambda: ListServiceTitlesHandler(self._directory))
        mediator.register(ListRemovedServices, lambda: ListRemovedServicesHandler(self._directory, clock))
        mediator.register(
            ListFreeSlots,
            lambda: ListFreeSlotsHandler(self._availability_reader, self._busy, self._finder, clock),
        )
        mediator.register(
            CheckBookableSlot,
            lambda: CheckBookableSlotHandler(
                self._page_reader, self._availability_reader, self._busy, self._finder, clock
            ),
        )
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def api_router(self, mediator: Mediator) -> APIRouter:
        """HTTP-роутер публичных эндпоинтов."""
        return TenancyApiController(mediator).router()

    def cabinet_router(
        self, mediator: Mediator, auth: MasterAuth, storage: FileStorage, api_prefix: str
    ) -> APIRouter:
        """HTTP-роутер кабинета мастера: профиль и настройки страницы, фото — в ``storage``."""
        return cabinet_router(mediator, auth, storage, self._deps.id_generator, api_prefix)

    def _uow(self) -> SqlAlchemyTenancyUnitOfWork:
        """Новый Unit of Work на каждый обработчик."""
        return SqlAlchemyTenancyUnitOfWork(self._deps.session_factory, self._deps.outbox_writer)
