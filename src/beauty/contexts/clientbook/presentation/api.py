"""HTTP API кабинета: клиенты мастера (``/me/clients``)."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``master``) — локальная переменная.
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from beauty.contexts.clientbook.application.commands import AddClientNote, RemoveClientNote, RenameClient
from beauty.contexts.clientbook.application.dto import ClientCardView, ClientRow, ClientVisit, NoteView
from beauty.contexts.clientbook.application.queries import GetClientCard, ListClients
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.web.auth import MasterAuth


class NameInput(BaseModel):
    """Имя клиента."""

    name: str | None = Field(max_length=60)


class NoteInput(BaseModel):
    """Заметка."""

    text: str = Field(min_length=1, max_length=500)


def _money(amount: int | None) -> dict[str, Any] | None:
    return None if amount is None else {"amount": amount, "currency": "KZT"}


def _iso(value: Any) -> str | None:
    return None if value is None else value.isoformat()


def render_row(row: ClientRow) -> dict[str, Any]:
    """``MasterClient`` контракта."""
    return {
        "id": str(row.client_id),
        "conversation_id": str(row.conversation_id),
        "display_name": row.display_name,
        "named": row.named,
        "phone_masked": row.phone_masked,
        "visits": row.visits,
        "last_visit_at": _iso(row.last_visit_at),
        "next_visit_at": _iso(row.next_visit_at),
        "notes": row.notes,
        "last_activity_at": row.last_activity_at.isoformat(),
    }


def _visit(visit: ClientVisit) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": str(visit.id),
        "status": visit.status,
        "start": visit.start.isoformat(),
        "end": visit.end.isoformat(),
        "service_title": visit.service_title,
        "price": _money(visit.price_amount),
    }
    if visit.cancelled_by:
        body["cancelled_by"] = visit.cancelled_by
    return body


def render_note(note: NoteView) -> dict[str, Any]:
    """``ClientNote`` контракта."""
    return {
        "id": str(note.id),
        "text": note.text,
        "author": note.author,
        "created_at": note.created_at.isoformat(),
    }


def render_card(card: ClientCardView) -> dict[str, Any]:
    """``MasterClientCard`` контракта."""
    return render_row(card.row) | {
        "since": card.since.isoformat(),
        "cancelled": card.cancelled,
        "upcoming": [_visit(v) for v in card.upcoming],
        "history": [_visit(v) for v in card.history],
        "note_items": [render_note(n) for n in card.notes],
    }


def clients_router(mediator: Mediator, auth: MasterAuth) -> APIRouter:
    """Роутер ``/me/clients``."""
    master = Annotated[UUID, Depends(auth)]
    router = APIRouter(prefix="/me/clients", tags=["master"])

    async def card(master_id: UUID, client_id: UUID, status_code: int = 200) -> JSONResponse:
        view = await mediator.send(GetClientCard(master_id, client_id))
        return JSONResponse(render_card(view), status_code=status_code)

    @router.get("", summary="Клиенты мастера")
    async def clients(
        master_id: master,
        q: Annotated[str | None, Query(max_length=60)] = None,
        filter_by: Annotated[Literal["all", "upcoming"], Query(alias="filter")] = "all",
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        page = await mediator.send(ListClients(master_id, q, filter_by == "upcoming", limit, offset))
        return {"items": [render_row(r) for r in page.items], "total": page.total}

    @router.get("/{client_id}", summary="Карточка клиента")
    async def get_card(client_id: UUID, master_id: master) -> JSONResponse:
        return await card(master_id, client_id)

    @router.put("/{client_id}/name", summary="Имя клиента")
    async def rename(client_id: UUID, body: NameInput, master_id: master) -> JSONResponse:
        await mediator.send(RenameClient(master_id, client_id, body.name))
        return await card(master_id, client_id)

    @router.post("/{client_id}/notes", status_code=201, summary="Добавить заметку")
    async def add_note(client_id: UUID, body: NoteInput, master_id: master) -> JSONResponse:
        await mediator.send(AddClientNote(master_id, client_id, body.text))
        return await card(master_id, client_id, status_code=201)

    @router.delete("/{client_id}/notes/{note_id}", summary="Удалить заметку")
    async def remove_note(client_id: UUID, note_id: UUID, master_id: master) -> JSONResponse:
        await mediator.send(RemoveClientNote(master_id, client_id, note_id))
        return await card(master_id, client_id)

    return router
