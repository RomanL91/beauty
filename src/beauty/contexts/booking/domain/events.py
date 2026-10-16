"""Доменные события Booking.

Каждое событие несёт полный снимок записи (``appointment`` — в форме контракта API)
и номер ревизии: подписчики (карточка заявки в переписке) обновляют свою копию,
не обращаясь к Booking, и не перетирают новое старым при переупорядочивании.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from beauty.shared.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class AppointmentEvent(DomainEvent):
    """Общая часть событий записи."""

    appointment_id: UUID
    master_id: UUID
    client_id: UUID
    revision: int
    appointment: dict[str, Any]
    reschedule_of: UUID | None = None


@dataclass(frozen=True, kw_only=True)
class AppointmentRequested(AppointmentEvent):
    """Клиент оставил заявку (или заявку на перенос)."""

    routing_key = "booking.appointment.requested"


@dataclass(frozen=True, kw_only=True)
class AppointmentConfirmed(AppointmentEvent):
    """Мастер подтвердил заявку."""

    routing_key = "booking.appointment.confirmed"


@dataclass(frozen=True, kw_only=True)
class AppointmentCancelled(AppointmentEvent):
    """Запись отменена: клиентом, мастером (отклонил) или системой (истекла)."""

    routing_key = "booking.appointment.cancelled"

    cancelled_by: str
    reason: str
    offer_alternatives: bool = False


@dataclass(frozen=True, kw_only=True)
class AppointmentReminderDue(AppointmentEvent):
    """Пора напомнить клиенту о визите."""

    routing_key = "booking.appointment.reminder_due"


@dataclass(frozen=True, kw_only=True)
class AppointmentCompleted(AppointmentEvent):
    """Визит состоялся."""

    routing_key = "booking.appointment.completed"
