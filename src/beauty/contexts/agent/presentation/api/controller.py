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
from beauty.contexts.agent.application.playbook import (
    AddPractice,
    EditPractice,
    GetPlaybook,
    PlaybookView,
    RemovePractice,
    SetBookingAutonomy,
)
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


class PracticeInput(BaseModel):
    """Запись опыта (``PracticeInput`` контракта)."""

    text: str = Field(min_length=1, max_length=500)
    service_id: UUID | None = None


class AutonomyInput(BaseModel):
    """Записывать клиентов сразу."""

    auto_confirm: bool


def render_playbook(view: PlaybookView) -> dict[str, Any]:
    """Опыт мастера → ``Playbook`` контракта."""
    return {
        "auto_confirm": view.auto_confirm,
        "practices": [
            {
                "id": str(p.id),
                "text": p.text,
                "service_id": None if p.service_id is None else str(p.service_id),
                "service_title": p.service_title,
                "author": p.author,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in view.practices
        ],
    }


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

    @router.get("/playbook", summary="Опыт мастера — что знает ассистент")
    async def playbook(master_id: master) -> dict[str, Any]:
        return render_playbook(await mediator.send(GetPlaybook(master_id)))

    @router.put("/playbook/autonomy", summary="Записывать клиентов сразу")
    async def autonomy(body: AutonomyInput, master_id: master) -> dict[str, Any]:
        return render_playbook(await mediator.send(SetBookingAutonomy(master_id, body.auto_confirm)))

    @router.post("/playbook/practices", status_code=201, summary="Добавить запись опыта")
    async def add_practice(body: PracticeInput, master_id: master) -> dict[str, Any]:
        return render_playbook(await mediator.send(AddPractice(master_id, body.text, body.service_id)))

    @router.put("/playbook/practices/{practice_id}", summary="Изменить запись опыта")
    async def edit_practice(practice_id: UUID, body: PracticeInput, master_id: master) -> dict[str, Any]:
        command = EditPractice(master_id, practice_id, body.text, body.service_id)
        return render_playbook(await mediator.send(command))

    @router.delete("/playbook/practices/{practice_id}", summary="Удалить запись опыта")
    async def remove_practice(practice_id: UUID, master_id: master) -> dict[str, Any]:
        return render_playbook(await mediator.send(RemovePractice(master_id, practice_id)))

    return router
