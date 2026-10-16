"""Unit of Work контекста Booking."""

from __future__ import annotations

from beauty.contexts.booking.application.ports import AppointmentTimers
from beauty.contexts.booking.domain.repositories import AppointmentRepository
from beauty.shared.application.uow import UnitOfWork


class BookingUnitOfWork(UnitOfWork):
    """Записи и их таймеры в одной транзакции."""

    appointments: AppointmentRepository
    timers: AppointmentTimers
