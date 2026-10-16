"""Кабинет мастера: чаты, ответы, обработчик диалога, поток событий."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``master``) — локальная переменная.
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from beauty.contexts.conversations.application.commands import (
    MarkConversationRead,
    PostMasterMessage,
    SetConversationHandler,
)
from beauty.contexts.conversations.application.queries import (
    GetConversationSummary,
    ListInbox,
    ListMasterMessages,
)
from beauty.contexts.conversations.domain.conversation import Handler
from beauty.contexts.conversations.presentation.api.master_stream import MasterEventsStream
from beauty.contexts.conversations.presentation.api.render import MessageRenderer, render_summary
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.web.auth import MasterAuth

SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


class MasterTextInput(BaseModel):
    """Ответ мастера (``TextInput`` контракта)."""

    client_id: UUID
    kind: Literal["text"]
    text: str = Field(min_length=1, max_length=4000)


class HandlerState(BaseModel):
    """Кто ведёт диалог."""

    handler: Literal["agent", "master"]


def cabinet_router(
    mediator: Mediator,
    auth: MasterAuth,
    hub: RealtimeHub,
    renderer: MessageRenderer,
    stream_max_duration: float,
) -> APIRouter:
    """Роутер ``/me`` Conversations — только переписки своего мастера (чужие — 404)."""
    master = Annotated[UUID, Depends(auth)]
    router = APIRouter(prefix="/me", tags=["master"])

    @router.get("/conversations", summary="Чаты мастера")
    async def inbox(
        master_id: master,
        filter_by: Annotated[str, Query(alias="filter")] = "all",
        q: Annotated[str | None, Query(max_length=100)] = None,
    ) -> dict[str, Any]:
        found = await mediator.send(ListInbox(master_id, filter_by, q))
        return {"items": [render_summary(item) for item in found.items], "counts": found.counts}

    @router.get("/conversations/{conversation_id}", summary="Шапка диалога")
    async def summary(conversation_id: UUID, master_id: master) -> dict[str, Any]:
        return render_summary(await mediator.send(GetConversationSummary(master_id, conversation_id)))

    @router.get("/conversations/{conversation_id}/messages", summary="История диалога")
    async def history(
        conversation_id: UUID,
        master_id: master,
        before: Annotated[UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        page = await mediator.send(ListMasterMessages(conversation_id, master_id, before, limit))
        if before is None:
            await mediator.send(MarkConversationRead(conversation_id, master_id))
        return {"items": [renderer.render(item) for item in page.items], "has_more": page.has_more}

    @router.post("/conversations/{conversation_id}/messages", status_code=201, summary="Ответить клиенту")
    async def reply(conversation_id: UUID, body: MasterTextInput, master_id: master) -> JSONResponse:
        sent = await mediator.send(PostMasterMessage(conversation_id, master_id, body.client_id, body.text))
        return JSONResponse(
            {"message": renderer.render(sent.message), "handler": sent.handler.value}, status_code=201
        )

    @router.put("/conversations/{conversation_id}/handler", summary="Кто ведёт диалог")
    async def set_handler(conversation_id: UUID, body: HandlerState, master_id: master) -> dict[str, str]:
        handler = await mediator.send(
            SetConversationHandler(conversation_id, master_id, Handler(body.handler))
        )
        return {"handler": handler.value}

    @router.get("/events", summary="SSE-поток кабинета мастера")
    async def events(
        request: Request,
        master_id: master,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        stream = MasterEventsStream(
            mediator,
            hub,
            renderer,
            master_id,
            resumed=last_event_id is not None,
            is_disconnected=request.is_disconnected,
            max_duration=stream_max_duration,
        )
        return StreamingResponse(stream.events(), media_type="text/event-stream", headers=SSE_HEADERS)

    return router
