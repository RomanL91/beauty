"""HTTP API переписки клиента."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``client``) — локальная переменная.
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile

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
from beauty.shared.application.errors import ApplicationError
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.storage import FileStorage
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.web.auth import BearerAuth

MAX_VOICE_BYTES = 5 * 1024 * 1024
VOICE_EXTENSIONS = {"audio/webm": ".webm", "audio/mp4": ".m4a", "audio/aac": ".m4a", "audio/ogg": ".ogg"}
SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


class InvalidVoiceError(ApplicationError):
    """Нужны поля audio (webm, mp4 или ogg), client_id и duration до 120 с."""

    code = "invalid_voice"


class VoiceTooLargeError(ApplicationError):
    """Голосовое больше 5 МБ."""

    code = "voice_too_large"


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
        self._storage = storage
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
        async with request.form(max_files=1, max_fields=4) as form:
            audio, raw_client_id, raw_duration = (
                form.get("audio"),
                form.get("client_id"),
                form.get("duration"),
            )
            if not isinstance(audio, UploadFile) or not isinstance(raw_client_id, str):
                raise InvalidVoiceError()
            try:
                client_message_id = UUID(raw_client_id)
                duration = float(raw_duration) if isinstance(raw_duration, str) else 0.0
            except ValueError as error:
                raise InvalidVoiceError() from error
            mime = (audio.content_type or "").split(";")[0].strip()
            extension = VOICE_EXTENSIONS.get(mime)
            if extension is None or not 0 < duration <= MAX_VOICE_SECONDS:
                raise InvalidVoiceError()
            if audio.size is not None and audio.size > MAX_VOICE_BYTES:
                raise VoiceTooLargeError()
            stored = await self._storage.save("voice", _chunks(audio), mime, extension)
        return PostClientMessage(
            conversation_id, client_id, client_message_id, VoiceBody(stored.key, duration)
        )


async def _chunks(upload: UploadFile, size: int = 64 * 1024) -> AsyncIterator[bytes]:
    total = 0
    while chunk := await upload.read(size):
        total += len(chunk)
        if total > MAX_VOICE_BYTES:
            raise VoiceTooLargeError()
        yield chunk


def _event_id(raw: str | None) -> int | None:
    """``Last-Event-ID`` → номер события (мусор — как отсутствие)."""
    if raw is None or not raw.strip().isdigit():
        return None
    return int(raw.strip())
