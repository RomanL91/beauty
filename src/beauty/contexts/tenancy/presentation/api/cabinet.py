"""Кабинет мастера: свой профиль (``GET /me``) и настройки страницы (``/me/settings`` и правки)."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``master``) — локальная переменная.
from collections.abc import Awaitable, Callable
from datetime import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from beauty.contexts.tenancy.application.commands import (
    AddPortfolioPhoto,
    AddService,
    ArchiveService,
    PublishMaster,
    RemovePortfolioPhoto,
    SetAvatar,
    SetBookingRules,
    SetDaysOff,
    SetWeeklySchedule,
    UnpublishMaster,
    UpdateMasterProfile,
    UpdateService,
)
from beauty.contexts.tenancy.application.queries import GetMasterPage, GetMasterSettings
from beauty.contexts.tenancy.domain.errors import InvalidWeeklySchedule
from beauty.contexts.tenancy.presentation.api.schemas import (
    BookingRulesSettingsModel,
    DaysOffInput,
    MasterPageResponse,
    MasterSettingsResponse,
    ProfileInput,
    ServiceInput,
    TimeIntervalModel,
    WorkingHoursInput,
)
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.storage import FileStorage
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.web.auth import MasterAuth
from beauty.shared.infrastructure.web.images import ImageUploadReader
from beauty.shared.infrastructure.web.media import PUBLIC_PREFIXES


def _time(value: str) -> time:
    """``HH:MM`` → время (неверное значение — ошибка расписания 422, а не 500)."""
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise InvalidWeeklySchedule(f"Время {value!r} — в формате ЧЧ:ММ") from error


def _interval(model: TimeIntervalModel) -> tuple[time, time]:
    return _time(model.start), _time(model.end)


class PhotoLinks:
    """Ссылки на фото из своего хранилища: ``<api>/media/public/<key>`` ↔ ключ."""

    def __init__(self, api_prefix: str) -> None:
        """Префикс API (``/api/v1``)."""
        self._prefix = f"{api_prefix.rstrip('/')}/media/public/"

    def url(self, key: str) -> str:
        """Ссылка на файл."""
        return f"{self._prefix}{key}"

    def key(self, url: str | None) -> str | None:
        """Ключ своего файла по ссылке (чужая ссылка — ``None``)."""
        if url is None or not url.startswith(self._prefix):
            return None
        key = url.removeprefix(self._prefix)
        return key if key.startswith(PUBLIC_PREFIXES) else None


def cabinet_router(
    mediator: Mediator, auth: MasterAuth, storage: FileStorage, ids: IdGenerator, api_prefix: str
) -> APIRouter:
    """Роутер ``/me`` Tenancy: только своя страница."""
    master = Annotated[UUID, Depends(auth)]
    router = APIRouter(prefix="/me", tags=["master"])

    async def settings(master_id: UUID, status_code: int = 200) -> JSONResponse:
        view = await mediator.send(GetMasterSettings(master_id))
        body = MasterSettingsResponse.of(view).model_dump(mode="json")
        return JSONResponse(body, status_code=status_code)

    @router.get("", response_model=MasterPageResponse, summary="Профиль мастера")
    async def me(master_id: master) -> MasterPageResponse:
        view = await mediator.send(GetMasterPage(master_id, published_only=False))
        return MasterPageResponse.of(view)

    @router.get("/settings", summary="Настройки страницы мастера")
    async def get_settings(master_id: master) -> JSONResponse:
        return await settings(master_id)

    @router.put("/profile", summary="Профиль страницы")
    async def profile(body: ProfileInput, master_id: master) -> JSONResponse:
        current = await mediator.send(GetMasterPage(master_id, published_only=False))
        await mediator.send(
            UpdateMasterProfile(
                master_id=master_id,
                display_name=body.display_name,
                name_nominative=body.name_forms.nominative,
                name_genitive=body.name_forms.genitive,
                name_dative=body.name_forms.dative,
                specialty=body.specialty,
                address=body.address,
                about=body.about,
                timezone=body.timezone,
                avatar_url=current.avatar_url,
            )
        )
        return await settings(master_id)

    @router.post("/services", status_code=201, summary="Добавить услугу")
    async def add_service(body: ServiceInput, master_id: master) -> JSONResponse:
        price = None if body.price is None else body.price.amount
        await mediator.send(AddService(master_id, body.title, body.duration_min, price))
        return await settings(master_id, status_code=201)

    @router.put("/services/{service_id}", summary="Изменить услугу")
    async def update_service(service_id: UUID, body: ServiceInput, master_id: master) -> JSONResponse:
        price = None if body.price is None else body.price.amount
        await mediator.send(UpdateService(master_id, service_id, body.title, body.duration_min, price))
        return await settings(master_id)

    @router.delete("/services/{service_id}", summary="Убрать услугу")
    async def archive_service(service_id: UUID, master_id: master) -> JSONResponse:
        await mediator.send(ArchiveService(master_id, service_id))
        return await settings(master_id)

    @router.put("/working-hours", summary="Рабочие часы по дням недели")
    async def working_hours(body: WorkingHoursInput, master_id: master) -> JSONResponse:
        days = {day.weekday: tuple(_interval(i) for i in day.intervals) for day in body.days}
        await mediator.send(SetWeeklySchedule(master_id, days))
        return await settings(master_id)

    @router.put("/days-off", summary="Выходные даты")
    async def days_off(body: DaysOffInput, master_id: master) -> JSONResponse:
        await mediator.send(SetDaysOff(master_id, tuple(body.days)))
        return await settings(master_id)

    @router.put("/booking-rules", summary="Правила записи")
    async def booking_rules(body: BookingRulesSettingsModel, master_id: master) -> JSONResponse:
        await mediator.send(
            SetBookingRules(
                master_id,
                body.confirm_within_hours,
                body.change_deadline_hours,
                body.min_notice_minutes,
                body.horizon_days,
                body.slot_step_minutes,
            )
        )
        return await settings(master_id)

    @router.post("/publish", summary="Открыть страницу клиентам")
    async def publish(master_id: master) -> JSONResponse:
        await mediator.send(PublishMaster(master_id))
        return await settings(master_id)

    @router.post("/unpublish", summary="Скрыть страницу")
    async def unpublish(master_id: master) -> JSONResponse:
        await mediator.send(UnpublishMaster(master_id))
        return await settings(master_id)

    router.include_router(photo_router(mediator, auth, storage, ids, api_prefix, settings))
    return router


def photo_router(
    mediator: Mediator,
    auth: MasterAuth,
    storage: FileStorage,
    ids: IdGenerator,
    api_prefix: str,
    settings: Callable[..., Awaitable[JSONResponse]],
) -> APIRouter:
    """Фото работ и аватар: файлы — в хранилище, ссылки — на странице."""
    master = Annotated[UUID, Depends(auth)]
    router = APIRouter()
    images = ImageUploadReader(storage)
    links = PhotoLinks(api_prefix)

    async def forget(url: str | None) -> None:
        key = links.key(url)
        if key is not None:
            await storage.delete(key)

    @router.post("/photos", status_code=201, summary="Добавить фото работы")
    async def add_photo(request: Request, master_id: master) -> JSONResponse:
        image = await images.read(request)
        try:
            await mediator.send(AddPortfolioPhoto(master_id, ids.new(), links.url(image.key), image.alt))
        except Exception:
            await storage.delete(image.key)  # фото не прошло (лимит, черновик) — файл не нужен
            raise
        return await settings(master_id, status_code=201)

    @router.delete("/photos/{photo_id}", summary="Убрать фото работы")
    async def remove_photo(photo_id: UUID, master_id: master) -> JSONResponse:
        await forget(await mediator.send(RemovePortfolioPhoto(master_id, photo_id)))
        return await settings(master_id)

    @router.put("/avatar", summary="Фото профиля")
    async def set_avatar(request: Request, master_id: master) -> JSONResponse:
        image = await images.read(request)
        await forget(await mediator.send(SetAvatar(master_id, links.url(image.key))))
        return await settings(master_id)

    @router.delete("/avatar", summary="Убрать фото профиля")
    async def remove_avatar(master_id: master) -> JSONResponse:
        await forget(await mediator.send(SetAvatar(master_id, None)))
        return await settings(master_id)

    return router
