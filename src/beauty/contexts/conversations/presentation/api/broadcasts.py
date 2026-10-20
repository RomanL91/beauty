"""Кабинет: рассылки объявлений (``/me/broadcasts``)."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``master``) — локальная переменная.
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from beauty.contexts.conversations.application.commands import (
    DiscardBroadcast,
    DraftBroadcast,
    EditBroadcast,
    SendBroadcast,
    SetBroadcastPhoto,
)
from beauty.contexts.conversations.application.dto import BroadcastView
from beauty.contexts.conversations.application.queries import GetBroadcast, ListBroadcasts
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.storage import FileStorage
from beauty.shared.infrastructure.storage.signing import SignedMediaUrls
from beauty.shared.infrastructure.web.auth import MasterAuth
from beauty.shared.infrastructure.web.images import ImageUploadReader

ANNOUNCEMENTS_NAMESPACE = "announcements"


class BroadcastInput(BaseModel):
    """Текст рассылки."""

    text: str = Field(min_length=1, max_length=1000)


def render_broadcast(view: BroadcastView, media: SignedMediaUrls) -> dict[str, Any]:
    """``Broadcast`` контракта."""

    def iso(value: Any) -> str | None:
        return None if value is None else value.isoformat()

    return {
        "id": str(view.id),
        "text": view.text,
        "photo_url": None if view.photo_key is None else media.url(view.photo_key),
        "status": view.status,
        "origin": view.origin,
        "recipients": view.recipients,
        "delivered": view.delivered,
        "created_at": view.created_at.isoformat(),
        "started_at": iso(view.started_at),
        "finished_at": iso(view.finished_at),
    }


def broadcasts_router(
    mediator: Mediator, auth: MasterAuth, storage: FileStorage, media: SignedMediaUrls
) -> APIRouter:
    """Роутер рассылок кабинета."""
    master = Annotated[UUID, Depends(auth)]
    router = APIRouter(prefix="/me/broadcasts", tags=["master"])
    images = ImageUploadReader(storage, ANNOUNCEMENTS_NAMESPACE)

    async def one(master_id: UUID, broadcast_id: UUID, status_code: int = 200) -> JSONResponse:
        view = await mediator.send(GetBroadcast(master_id, broadcast_id))
        return JSONResponse(render_broadcast(view, media), status_code=status_code)

    @router.get("", summary="Рассылки мастера")
    async def listing(master_id: master) -> dict[str, Any]:
        view = await mediator.send(ListBroadcasts(master_id))
        return {
            "items": [render_broadcast(item, media) for item in view.items],
            "allowed": view.allowed,
            "next_at": None if view.next_at is None else view.next_at.isoformat(),
        }

    @router.post("", status_code=201, summary="Черновик рассылки")
    async def draft(body: BroadcastInput, master_id: master) -> JSONResponse:
        broadcast_id = await mediator.send(DraftBroadcast(master_id, body.text))
        return await one(master_id, broadcast_id, status_code=201)

    @router.get("/{broadcast_id}", summary="Рассылка")
    async def get(broadcast_id: UUID, master_id: master) -> JSONResponse:
        return await one(master_id, broadcast_id)

    @router.put("/{broadcast_id}", summary="Изменить текст черновика")
    async def edit(broadcast_id: UUID, body: BroadcastInput, master_id: master) -> JSONResponse:
        await mediator.send(EditBroadcast(master_id, broadcast_id, body.text))
        return await one(master_id, broadcast_id)

    @router.delete("/{broadcast_id}", status_code=204, summary="Удалить черновик")
    async def discard(broadcast_id: UUID, master_id: master) -> Response:
        await mediator.send(DiscardBroadcast(master_id, broadcast_id))
        return Response(status_code=204)

    @router.put("/{broadcast_id}/photo", summary="Фото к черновику")
    async def photo(broadcast_id: UUID, request: Request, master_id: master) -> JSONResponse:
        await mediator.send(GetBroadcast(master_id, broadcast_id))  # чужая — 404 до записи файла
        upload = await images.read(request)
        await mediator.send(SetBroadcastPhoto(master_id, broadcast_id, upload.key))
        return await one(master_id, broadcast_id)

    @router.delete("/{broadcast_id}/photo", summary="Убрать фото")
    async def remove_photo(broadcast_id: UUID, master_id: master) -> JSONResponse:
        await mediator.send(SetBroadcastPhoto(master_id, broadcast_id, None))
        return await one(master_id, broadcast_id)

    @router.post("/{broadcast_id}/send", summary="Отправить всем клиентам")
    async def send(broadcast_id: UUID, master_id: master) -> JSONResponse:
        await mediator.send(SendBroadcast(master_id, broadcast_id))
        return await one(master_id, broadcast_id)

    return router
