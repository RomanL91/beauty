"""Value objects контекста Booking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from beauty.contexts.booking.domain.errors import InvalidTimeSlot

MAX_DURATION = timedelta(hours=12)


class AppointmentStatus(StrEnum):
    """Статус записи."""

    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class CancelledBy(StrEnum):
    """Кто отменил запись."""

    CLIENT = "client"
    MASTER = "master"
    SYSTEM = "system"


class CancelReason(StrEnum):
    """Почему запись отменена."""

    CLIENT_CANCELLED = "client_cancelled"
    DECLINED = "declined"
    EXPIRED = "expired"
    RESCHEDULED = "rescheduled"


@dataclass(frozen=True, slots=True)
class TimeSlot:
    """Время визита ``[start, end)``; хранится в UTC."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        """Проверить интервал и привести к UTC."""
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise InvalidTimeSlot("Время записи — с часовым поясом")
        object.__setattr__(self, "start", self.start.astimezone(UTC))
        object.__setattr__(self, "end", self.end.astimezone(UTC))
        if not timedelta(0) < self.end - self.start <= MAX_DURATION:
            raise InvalidTimeSlot("Визит — от минуты до 12 часов")


@dataclass(frozen=True, slots=True)
class ServiceSnapshot:
    """Услуга на момент заявки: цена и длительность не меняются задним числом."""

    service_id: UUID
    title: str
    duration_min: int
    price_amount: int | None


@dataclass(frozen=True, slots=True)
class ClientSnapshot:
    """Клиент глазами мастера на момент заявки."""

    display_name: str
    phone_masked: str
    visit_number: int

    @classmethod
    def new_client(cls, phone_e164: str, visit_number: int) -> ClientSnapshot:
        """Клиент без имени: «Новый клиент · …89 67»."""
        digits = phone_e164.removeprefix("+")
        tail = f"{digits[-4:-2]} {digits[-2:]}"
        if phone_e164.startswith("+7") and len(digits) == 11:
            masked = f"+7 {digits[1:4]} ••• {tail}"
        else:
            masked = f"+{digits[:-7]} ••• {tail}"
        return cls(display_name=f"Новый клиент · …{tail}", phone_masked=masked, visit_number=visit_number)
