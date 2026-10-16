"""HTTP API переписки клиента."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``client``) — локальная переменная.
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from beauty.contexts.conversations.application.commands import (
    OpenConversation,
    PostClientMessage,
    VoiceBody,
)
from beauty.contexts.conversations.application.queries import GetMyConversation, ListMessages, ReadFeed
from beauty.contexts.conversations.domain.content import MAX_VOICE_SECONDS
from beauty.contexts.conversations.presentation.api.render import MessageRenderer
from beauty.contexts.conversations.presentation.api.schemas import CLIENT_INPUT
from beauty.contexts.conversations.presentation.api.stream import ConversationFeedStream
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.storage import FileStorage
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.web.auth import BearerAuth
from beauty.shared.infrastructure.web.voice import VoiceUploadReader

SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


class ConversationsApiController:
    """``/conversations`` — только своя переписка (чужая неотличима от несуществующей)."""

    def __init__(
        self,
        mediator: Mediator,
        auth: BearerAuth,
        hub: RealtimeHub,
        storage: FileStorage,
        renderer: MessageRenderer,
        poll_interval: float,
        max_duration: float,
    ) -> None:
        """Получить зависимости."""
        self._mediator = mediator
        self._auth = auth
        self._hub = hub
        self._voices = VoiceUploadReader(storage, MAX_VOICE_SECONDS)
        self._renderer = renderer
        self._poll_interval = poll_interval
        self._max_duration = max_duration

    def router(self) -> APIRouter:
        """Роутер переписки."""
        mediator, renderer = self._mediator, self._renderer
        client = Annotated[UUID, Depends(self._auth)]
        router = APIRouter(prefix="/conversations", tags=["client"])

        @router.get("/me", summary="Моя переписка с мастером")
        async def my_conversation(master: Annotated[str, Query()], client_id: client) -> dict[str, Any]:
            found = await mediator.send(GetMyConversation(master, client_id))
            return {"id": str(found.id), "master_slug": found.master_slug}

        @router.post("/me", summary="Открыть переписку (идемпотентно)")
        async def open_conversation(master: Annotated[str, Query()], client_id: client) -> JSONResponse:
            opened = await mediator.send(OpenConversation(master, client_id))
            return JSONResponse(
                {"id": str(opened.id), "master_slug": opened.master_slug},
                status_code=201 if opened.created else 200,
            )

        @router.get("/{conversation_id}/messages", summary="История сообщений")
        async def history(
            conversation_id: UUID,
            client_id: client,
            before: Annotated[UUID | None, Query()] = None,
            limit: Annotated[int, Query(ge=1, le=100)] = 30,
        ) -> dict[str, Any]:
            page = await mediator.send(ListMessages(conversation_id, client_id, before, limit))
            return {"items": [renderer.render(item) for item in page.items], "has_more": page.has_more}

        @router.post("/{conversation_id}/messages", status_code=201, summary="Отправить сообщение")
        async def send(conversation_id: UUID, request: Request, client_id: client) -> JSONResponse:
            if request.headers.get("Content-Type", "").startswith("multipart/form-data"):
                command = await self._voice(request, conversation_id, client_id)
            else:
                command = await self._json(request, conversation_id, client_id)
            view = await mediator.send(command)
            return JSONResponse(renderer.render(view), status_code=201)

        @router.get("/{conversation_id}/events", summary="SSE-поток переписки")
        async def events(
            conversation_id: UUID,
            request: Request,
            client_id: client,
            last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
        ) -> StreamingResponse:
            await mediator.send(ReadFeed(conversation_id, client_id))  # 404 — до начала потока
            stream = ConversationFeedStream(
                mediator,
                self._hub,
                renderer,
                conversation_id,
                client_id,
                after=_event_id(last_event_id),
                is_disconnected=request.is_disconnected,
                poll_interval=self._poll_interval,
                max_duration=self._max_duration,
            )
            return StreamingResponse(stream.events(), media_type="text/event-stream", headers=SSE_HEADERS)

        return router

    @staticmethod
    async def _json(request: Request, conversation_id: UUID, client_id: UUID) -> PostClientMessage:
        try:
            parsed = CLIENT_INPUT.validate_json(await request.body())
        except ValidationError as error:
            raise RequestValidationError(
                [{**item, "loc": ("body", *item["loc"])} for item in error.errors()]
            ) from error
        return PostClientMessage(conversation_id, client_id, parsed.client_id, parsed.body())

    async def _voice(self, request: Request, conversation_id: UUID, client_id: UUID) -> PostClientMessage:
        voice = await self._voices.read(request)
        return PostClientMessage(
            conversation_id, client_id, voice.client_message_id, VoiceBody(voice.audio_key, voice.duration)
        )


def _event_id(raw: str | None) -> int | None:
    """``Last-Event-ID`` → номер события (мусор — как отсутствие)."""
    if raw is None or not raw.strip().isdigit():
        return None
    return int(raw.strip())
