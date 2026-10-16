"""Агрегат ``Appointment`` — запись клиента к мастеру.

Жизненный цикл::

    requested ──confirm──▶ confirmed ──complete──▶ completed
        │                      │
        └─decline/expire/      └─cancel (клиент до дедлайна) / supersede (перенос)
          cancel/supersede ──▶ cancelled

Заявка держит окно за клиентом до ``hold_until``: столько у мастера есть на ответ,
потом заявка отклоняется системой. «Одно время — одна запись» гарантирует
исключающее ограничение БД, а не агрегат: агрегат не видит чужих записей.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.booking.domain.errors import (
    AppointmentClosed,
    AppointmentNotPending,
    ChangeDeadlinePassed,
    InvalidTimeSlot,
    RequestExpired,
)
from beauty.contexts.booking.domain.events import (
    AppointmentCancelled,
    AppointmentCompleted,
    AppointmentConfirmed,
    AppointmentRequested,
)
from beauty.contexts.booking.domain.value_objects import (
    AppointmentStatus,
    CancelledBy,
    CancelReason,
    ClientSnapshot,
    ServiceSnapshot,
    TimeSlot,
)
from beauty.shared.domain.aggregate import AggregateRoot

OPEN_STATUSES = frozenset({AppointmentStatus.REQUESTED, AppointmentStatus.CONFIRMED})


class Appointment(AggregateRoot):
    """Заявка или запись."""

    def __init__(
        self,
        appointment_id: UUID,
        master_id: UUID,
        client_id: UUID,
        service: ServiceSnapshot,
        client: ClientSnapshot,
        slot: TimeSlot,
        timezone: str,
        hold_until: datetime,
        change_deadline_hours: int,
        reschedule_of: UUID | None,
        created_at: datetime,
    ) -> None:
        """Создать заявку (используйте ``request``)."""
        self.id = appointment_id
        self.master_id = master_id
        self.client_id = client_id
        self.service = service
        self.client = client
        self.slot = slot
        self.timezone = timezone
        self.status = AppointmentStatus.REQUESTED
        self.hold_until = hold_until
        self.change_deadline_hours = change_deadline_hours
        self.reschedule_of = reschedule_of
        self.confirmed_at: datetime | None = None
        self.cancelled_at: datetime | None = None
        self.cancelled_by: CancelledBy | None = None
        self.cancel_reason: CancelReason | None = None
        self.completed_at: datetime | None = None
        self.revision = 1
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def request(
        cls,
        *,
        appointment_id: UUID,
        master_id: UUID,
        client_id: UUID,
        service: ServiceSnapshot,
        client: ClientSnapshot,
        slot: TimeSlot,
        timezone: str,
        confirm_within: timedelta,
        change_deadline_hours: int,
        now: datetime,
        reschedule_of: UUID | None = None,
    ) -> Appointment:
        """Оставить заявку; окно держится до ответа мастера, но не дольше начала визита."""
        if slot.start <= now:
            raise InvalidTimeSlot("Нельзя записаться на прошедшее время")
        appointment = cls(
            appointment_id,
            master_id,
            client_id,
            service,
            client,
            slot,
            timezone,
            min(now + confirm_within, slot.start),
            change_deadline_hours,
            reschedule_of,
            now,
        )
        appointment._record(AppointmentRequested(**appointment._event_fields(now)))
        return appointment

    @property
    def is_open(self) -> bool:
        """Заявка или подтверждённая запись (держит окно)."""
        return self.status in OPEN_STATUSES

    @property
    def change_deadline(self) -> datetime:
        """До какого момента клиент может перенести или отменить запись."""
        return self.slot.start - timedelta(hours=self.change_deadline_hours)

    def confirm(self, now: datetime) -> bool:
        """Мастер подтвердил; повторное подтверждение — no-op (``False``)."""
        if self.status is AppointmentStatus.CONFIRMED:
            return False
        self._require_pending()
        if now >= self.hold_until:
            raise RequestExpired()
        self.status = AppointmentStatus.CONFIRMED
        self.confirmed_at = now
        self._touch(now)
        self._record(AppointmentConfirmed(**self._event_fields(now)))
        return True

    def decline(self, now: datetime, *, offer_alternatives: bool = False) -> bool:
        """Мастер отклонил заявку; ``offer_alternatives`` — клиенту предложат другие окна."""
        if self.cancel_reason is CancelReason.DECLINED:
            return False
        self._require_pending()
        self._cancel(CancelledBy.MASTER, CancelReason.DECLINED, now, offer_alternatives=offer_alternatives)
        return True

    def expire(self, now: datetime) -> bool:
        """Мастер не ответил вовремя: заявка отклоняется системой."""
        if self.status is not AppointmentStatus.REQUESTED or now < self.hold_until:
            return False
        self._cancel(CancelledBy.SYSTEM, CancelReason.EXPIRED, now)
        return True

    def cancel_by_client(self, now: datetime) -> bool:
        """Клиент отменил заявку или запись; уже отменённая — no-op."""
        if self.status is AppointmentStatus.CANCELLED:
            return False
        self.ensure_changeable(now)
        self._cancel(CancelledBy.CLIENT, CancelReason.CLIENT_CANCELLED, now)
        return True

    def ensure_changeable(self, now: datetime) -> None:
        """Клиент может менять запись: она открыта, и дедлайн не прошёл.

        Неподтверждённую заявку можно отозвать в любой момент до начала визита.
        """
        if not self.is_open:
            raise AppointmentClosed()
        limit = self.change_deadline if self.status is AppointmentStatus.CONFIRMED else self.slot.start
        if now >= limit:
            raise ChangeDeadlinePassed()

    def supersede(self, now: datetime) -> bool:
        """Запись заменена подтверждённым переносом — окно освобождается."""
        if not self.is_open:
            return False
        self._cancel(CancelledBy.CLIENT, CancelReason.RESCHEDULED, now)
        return True

    def complete(self, now: datetime) -> bool:
        """Визит прошёл."""
        if self.status is not AppointmentStatus.CONFIRMED or now < self.slot.end:
            return False
        self.status = AppointmentStatus.COMPLETED
        self.completed_at = now
        self._touch(now)
        self._record(AppointmentCompleted(**self._event_fields(now)))
        return True

    def snapshot(self) -> dict[str, Any]:
        """Запись в форме контракта API (``Appointment``); время — в поясе мастера."""
        zone = ZoneInfo(self.timezone)
        price = self.service.price_amount
        payload: dict[str, Any] = {
            "id": str(self.id),
            "status": self.status.value,
            "service": {
                "id": str(self.service.service_id),
                "title": self.service.title,
                "duration_min": self.service.duration_min,
                "price": None if price is None else {"amount": price, "currency": "KZT"},
            },
            "start": self.slot.start.astimezone(zone).isoformat(),
            "end": self.slot.end.astimezone(zone).isoformat(),
            "client": {
                "id": str(self.client_id),
                "display_name": self.client.display_name,
                "phone_masked": self.client.phone_masked,
                "visit_number": self.client.visit_number,
            },
        }
        if self.status is AppointmentStatus.REQUESTED:
            hold = self.hold_until.astimezone(zone).isoformat()
            payload |= {"hold_until": hold, "auto_decline_at": hold}
        elif self.status is AppointmentStatus.CONFIRMED and self.confirmed_at is not None:
            payload |= {"confirmed_at": self.confirmed_at.astimezone(zone).isoformat(), "reminder": "none"}
        elif self.status is AppointmentStatus.CANCELLED and self.cancelled_by is not None:
            payload["cancelled_by"] = self.cancelled_by.value
        return payload

    def _require_pending(self) -> None:
        if self.status is not AppointmentStatus.REQUESTED:
            raise AppointmentNotPending()

    def _cancel(
        self, by: CancelledBy, reason: CancelReason, now: datetime, *, offer_alternatives: bool = False
    ) -> None:
        self.status = AppointmentStatus.CANCELLED
        self.cancelled_at = now
        self.cancelled_by = by
        self.cancel_reason = reason
        self._touch(now)
        event = AppointmentCancelled(
            **self._event_fields(now),
            cancelled_by=by.value,
            reason=reason.value,
            offer_alternatives=offer_alternatives,
        )
        self._record(event)

    def _touch(self, now: datetime) -> None:
        self.revision += 1
        self.updated_at = now

    def _event_fields(self, now: datetime) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "occurred_at": now,
            "appointment_id": self.id,
            "master_id": self.master_id,
            "client_id": self.client_id,
            "revision": self.revision,
            "appointment": self.snapshot(),
            "reschedule_of": self.reschedule_of,
        }
        return fields
