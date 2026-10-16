"""Публичный HTTP API Tenancy: страница мастера и свободные окна."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from beauty.contexts.tenancy.application.queries import GetMasterPage, ListFreeSlots
from beauty.contexts.tenancy.presentation.api.schemas import MasterPageResponse, SlotsResponse
from beauty.shared.application.mediator import Mediator

PAGE_CACHE = "public, max-age=60"


class TenancyApiController:
    """Эндпоинты без авторизации: их видит любой посетитель страницы мастера.

    Страница кэшируется на минуту (CDN/браузер), окна — нет: их состав меняется
    с каждой записью.
    """

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    def router(self) -> APIRouter:
        """Роутер ``/masters``."""
        router = APIRouter(prefix="/masters", tags=["public"])
        router.add_api_route(
            "/{slug}",
            self.master_page,
            methods=["GET"],
            response_model=MasterPageResponse,
            summary="Публичная страница мастера",
        )
        router.add_api_route(
            "/{slug}/slots",
            self.free_slots,
            methods=["GET"],
            response_model=SlotsResponse,
            summary="Свободные окна",
        )
        return router

    async def master_page(self, slug: str, response: Response) -> MasterPageResponse:
        """Профиль, услуги, работы и правила записи."""
        view = await self._mediator.send(GetMasterPage(slug))
        response.headers["Cache-Control"] = PAGE_CACHE
        return MasterPageResponse.of(view)

    async def free_slots(
        self,
        slug: str,
        response: Response,
        service: Annotated[UUID | None, Query()] = None,
        window_from: Annotated[datetime | None, Query(alias="from")] = None,
        window_to: Annotated[datetime | None, Query(alias="to")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> SlotsResponse:
        """Окна для услуги (или для самой короткой)."""
        slots = await self._mediator.send(
            ListFreeSlots(slug, service_id=service, window_from=window_from, window_to=window_to, limit=limit)
        )
        response.headers["Cache-Control"] = "no-store"
        return SlotsResponse.of(slots)
