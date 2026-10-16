"""Прикладные ошибки Booking."""

from __future__ import annotations

from beauty.shared.application.errors import ConflictError, NotFoundError


class AppointmentNotFoundError(NotFoundError):
    """Запись не найдена."""

    code = "appointment_not_found"


class SlotUnavailableError(ConflictError):
    """Это время недоступно для записи."""

    code = "slot_unavailable"


class SlotTakenError(SlotUnavailableError):
    """Это время только что заняли."""

    code = "slot_taken"
