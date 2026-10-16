"""``/me/assistant`` — лента поручений мастера его ИИ-администратору."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``master``) — локальная переменная.
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from beauty.contexts.agent.application.office import AnswerOfficeChoice, GiveOfficeTask, ListOfficeMessages
from beauty.contexts.agent.presentation.api.render import OfficeRenderer
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.web.auth import MasterAuth
from beauty.shared.infrastructure.web.voice import VoiceUploadReader


class TaskTextInput(BaseModel):
    """Поручение текстом (``TextInput`` контракта)."""

    client_id: UUID
    kind: Literal["text"]
    text: str = Field(min_length=1, max_length=4000)


class ChoiceAnswer(BaseModel):
    """Выбранный вариант."""

    option_id: str = Field(min_length=1, max_length=40)


def office_router(
    mediator: Mediator, auth: MasterAuth, renderer: OfficeRenderer, voices: VoiceUploadReader
) -> APIRouter:
    """Роутер ``/me/assistant`` — только своя лента (чужая карточка — 404)."""
    master = Annotated[UUID, Depends(auth)]
    router = APIRouter(prefix="/me/assistant", tags=["assistant"])

    @router.get("/messages", summary="Лента поручений")
    async def history(
        master_id: master,
        before: Annotated[UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        page = await mediator.send(ListOfficeMessages(master_id, before, limit))
        return {"items": [renderer.render(item) for item in page.items], "has_more": page.has_more}

    @router.post("/messages", status_code=201, summary="Дать поручение")
    async def give(request: Request, master_id: master) -> JSONResponse:
        if request.headers.get("Content-Type", "").startswith("multipart/form-data"):
            voice = await voices.read(request)
            command = GiveOfficeTask(
                master_id, voice.client_message_id, voice=(voice.audio_key, voice.duration)
            )
        else:
            try:
                body = TaskTextInput.model_validate_json(await request.body())
            except ValidationError as error:
                raise RequestValidationError(
                    [{**item, "loc": ("body", *item["loc"])} for item in error.errors()]
                ) from error
            command = GiveOfficeTask(master_id, body.client_id, text=body.text)
        return JSONResponse(renderer.render(await mediator.send(command)), status_code=201)

    @router.post("/choices/{choice_id}", summary="Выбрать вариант")
    async def choose(choice_id: UUID, body: ChoiceAnswer, master_id: master) -> dict[str, Any]:
        return renderer.render(await mediator.send(AnswerOfficeChoice(master_id, choice_id, body.option_id)))

    return router
