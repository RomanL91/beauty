"""HTTP API Booking: отмена и перенос записи клиентом."""

# Без ``from __future__ import annotations``: FastAPI читает аннотации маршрутов-замыканий,
# а алиас зависимости (``client``) — локальная переменная.
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from pydantic import AwareDatetime, BaseModel, Field

from beauty.contexts.booking.application.commands import CancelAppointment, RescheduleAppointment
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.web.auth import BearerAuth


class CancelRequest(BaseModel):
    """Тело отмены (причина пока не хранится)."""

    reason: str | None = Field(default=None, max_length=500)


class RescheduleRequest(BaseModel):
    """Новое время визита."""

    start: AwareDatetime


class BookingApiController:
    """Эндпоинты ``/appointments`` — только своя запись (чужая — 404).

    Ответ — снимок записи в форме контракта (``Appointment``), тот же, что в карточке
    заявки в переписке.
    """

    def __init__(self, mediator: Mediator, auth: BearerAuth) -> None:
        """Получить медиатор и аутентификацию."""
        self._mediator = mediator
        self._auth = auth

    def router(self) -> APIRouter:
        """Роутер записей клиента."""
        mediator = self._mediator
        client = Annotated[UUID, Depends(self._auth)]
        router = APIRouter(prefix="/appointments", tags=["client"])

        @router.post("/{appointment_id}/cancel", summary="Отменить запись")
        async def cancel(
            appointment_id: UUID,
            client_id: client,
            body: Annotated[CancelRequest | None, Body()] = None,
        ) -> dict[str, Any]:
            return await mediator.send(CancelAppointment(appointment_id, client_id))

        @router.post("/{appointment_id}/reschedule", summary="Перенести запись")
        async def reschedule(
            appointment_id: UUID,
            body: RescheduleRequest,
            client_id: client,
        ) -> dict[str, Any]:
            return await mediator.send(RescheduleAppointment(appointment_id, client_id, body.start))

        return router
