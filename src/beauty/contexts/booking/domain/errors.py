"""Доменные ошибки контекста Booking."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError, InvariantViolation


class InvalidTimeSlot(DomainError):
    """Некорректный интервал записи."""

    code = "invalid_time_slot"


class AppointmentNotPending(InvariantViolation):
    """Заявка уже рассмотрена: подтвердить или отклонить её нельзя."""

    code = "appointment_not_pending"


class RequestExpired(InvariantViolation):
    """Срок подтверждения заявки истёк — окно уже освобождено."""

    code = "request_expired"


class AppointmentClosed(InvariantViolation):
    """Запись уже отменена или состоялась."""

    code = "appointment_closed"


class ChangeDeadlinePassed(InvariantViolation):
    """Перенести или отменить запись уже нельзя — до визита слишком мало времени."""

    code = "change_deadline_passed"
