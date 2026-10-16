"""Кабинет мастера: график дня и решения по заявкам."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``master``) — локальная переменная.
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from beauty.contexts.booking.application.commands import ConfirmAppointment, DeclineAppointment
from beauty.contexts.booking.application.queries import GetDaySchedule
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.web.auth import MasterAuth


class DeclineRequest(BaseModel):
    """Отклонение заявки."""

    offer_alternatives: bool = False
    reason: str | None = Field(default=None, max_length=500)


def cabinet_router(mediator: Mediator, auth: MasterAuth) -> APIRouter:
    """Роутер ``/me`` Booking — только записи своего мастера (чужие — 404)."""
    master = Annotated[UUID, Depends(auth)]
    router = APIRouter(prefix="/me", tags=["master"])

    @router.get("/schedule", summary="График дня и обзор недели")
    async def schedule(master_id: master, day: Annotated[date, Query(alias="date")]) -> dict[str, Any]:
        return await mediator.send(GetDaySchedule(master_id, day))

    @router.post("/appointments/{appointment_id}/confirm", summary="Подтвердить заявку")
    async def confirm(appointment_id: UUID, master_id: master) -> dict[str, Any]:
        return await mediator.send(ConfirmAppointment(appointment_id, master_id))

    @router.post("/appointments/{appointment_id}/decline", summary="Отклонить заявку")
    async def decline(
        appointment_id: UUID,
        master_id: master,
        body: Annotated[DeclineRequest | None, Body()] = None,
    ) -> dict[str, Any]:
        offer = body.offer_alternatives if body is not None else False
        return await mediator.send(DeclineAppointment(appointment_id, master_id, offer_alternatives=offer))

    return router
