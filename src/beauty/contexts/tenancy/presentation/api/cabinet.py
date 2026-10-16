"""Кабинет мастера: свой профиль (``GET /me``)."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``master``) — локальная переменная.
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from beauty.contexts.tenancy.application.queries import GetMasterPage
from beauty.contexts.tenancy.presentation.api.schemas import MasterPageResponse
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.web.auth import MasterAuth


def cabinet_router(mediator: Mediator, auth: MasterAuth) -> APIRouter:
    """Роутер ``/me`` Tenancy."""
    master = Annotated[UUID, Depends(auth)]
    router = APIRouter(prefix="/me", tags=["master"])

    @router.get("", response_model=MasterPageResponse, summary="Профиль мастера")
    async def me(master_id: master) -> MasterPageResponse:
        view = await mediator.send(GetMasterPage(master_id, published_only=False))
        return MasterPageResponse.of(view)

    return router
