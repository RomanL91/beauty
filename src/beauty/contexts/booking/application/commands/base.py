"""Общая часть обработчиков команд Booking."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.booking.application.errors import AppointmentNotFoundError
from beauty.contexts.booking.application.uow import BookingUnitOfWork
from beauty.contexts.booking.domain.appointment import Appointment

type AppointmentPayload = dict[str, Any]
"""Снимок записи в форме контракта API (см. ``Appointment.snapshot``)."""


async def load(
    uow: BookingUnitOfWork,
    appointment_id: UUID,
    client_id: UUID | None = None,
    master_id: UUID | None = None,
) -> Appointment:
    """Запись по id; с ``client_id``/``master_id`` — только своя (чужая неотличима от несуществующей)."""
    appointment = await uow.appointments.get(appointment_id)
    if (
        appointment is None
        or (client_id is not None and appointment.client_id != client_id)
        or (master_id is not None and appointment.master_id != master_id)
    ):
        raise AppointmentNotFoundError()
    return appointment


async def withdraw_reschedules(uow: BookingUnitOfWork, appointment: Appointment, now: datetime) -> None:
    """Отозвать неподтверждённые заявки на перенос этой записи."""
    for pending in await uow.appointments.pending_reschedules(appointment.id):
        if pending.cancel_by_client(now):
            await uow.timers.cancel(pending.id)
