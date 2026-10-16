"""Агрегат Appointment: переходы, удержание, дедлайн, снимок."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from beauty.contexts.booking.domain.appointment import Appointment
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
    TimeSlot,
)
from tests.unit.booking.fakes import SERVICE

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
START = datetime(2026, 10, 17, 5, 0, tzinfo=UTC)  # сб 10:00 в Алматы


def requested(start: datetime = START, now: datetime = NOW) -> Appointment:
    """Свежая заявка (удержание 2 ч, дедлайн 12 ч)."""
    return Appointment.request(
        appointment_id=UUID(int=1),
        master_id=UUID(int=2),
        client_id=UUID(int=3),
        service=SERVICE,
        client=ClientSnapshot.new_client("+77051238967", 1),
        slot=TimeSlot(start, start + timedelta(hours=1)),
        timezone="Asia/Almaty",
        confirm_within=timedelta(hours=2),
        change_deadline_hours=12,
        now=now,
    )


def test_request_holds_slot_and_publishes_snapshot() -> None:
    appointment = requested()
    assert appointment.status is AppointmentStatus.REQUESTED
    assert appointment.hold_until == NOW + timedelta(hours=2)
    (event,) = appointment.pull_events()
    assert isinstance(event, AppointmentRequested)
    assert event.revision == 1
    assert event.appointment == {
        "id": str(UUID(int=1)),
        "status": "requested",
        "service": {
            "id": str(SERVICE.service_id),
            "title": "Массаж спины",
            "duration_min": 60,
            "price": {"amount": 1_200_000, "currency": "KZT"},
        },
        "start": "2026-10-17T10:00:00+05:00",
        "end": "2026-10-17T11:00:00+05:00",
        "client": {
            "id": str(UUID(int=3)),
            "display_name": "Новый клиент · …89 67",
            "phone_masked": "+7 705 ••• 89 67",
            "visit_number": 1,
        },
        "hold_until": "2026-10-15T19:00:00+05:00",
        "auto_decline_at": "2026-10-15T19:00:00+05:00",
    }


def test_hold_never_outlives_the_visit_and_past_is_rejected() -> None:
    soon = NOW + timedelta(minutes=30)
    assert requested(start=soon).hold_until == soon
    with pytest.raises(InvalidTimeSlot):
        requested(start=NOW - timedelta(minutes=1))
    with pytest.raises(InvalidTimeSlot):
        TimeSlot(START, START)
    with pytest.raises(InvalidTimeSlot):
        TimeSlot(START.replace(tzinfo=None), START + timedelta(hours=1))


def test_confirm_then_complete() -> None:
    appointment = requested()
    appointment.pull_events()
    assert appointment.confirm(NOW + timedelta(minutes=10))
    assert not appointment.confirm(NOW + timedelta(minutes=11))
    assert not appointment.complete(START)
    assert appointment.complete(START + timedelta(hours=1))
    confirmed, completed = appointment.pull_events()
    assert isinstance(confirmed, AppointmentConfirmed)
    assert confirmed.appointment["confirmed_at"] == "2026-10-15T17:10:00+05:00"
    assert confirmed.appointment["reminder"] == "none"
    assert isinstance(completed, AppointmentCompleted)
    assert completed.revision == 3
    assert completed.appointment["status"] == "completed"


def test_confirm_after_hold_is_rejected_and_expire_releases() -> None:
    appointment = requested()
    late = NOW + timedelta(hours=2)
    with pytest.raises(RequestExpired):
        appointment.confirm(late)
    assert not appointment.expire(late - timedelta(seconds=1))
    assert appointment.expire(late)
    assert not appointment.expire(late)
    assert (appointment.cancelled_by, appointment.cancel_reason) == (CancelledBy.SYSTEM, CancelReason.EXPIRED)
    event = appointment.pull_events()[-1]
    assert isinstance(event, AppointmentCancelled)
    assert event.appointment["cancelled_by"] == "system"
    assert (event.cancelled_by, event.reason) == ("system", "expired")


def test_decline_only_pending() -> None:
    appointment = requested()
    assert appointment.decline(NOW)
    assert not appointment.decline(NOW)
    assert appointment.cancelled_by is CancelledBy.MASTER
    confirmed = requested()
    confirmed.confirm(NOW)
    with pytest.raises(AppointmentNotPending):
        confirmed.decline(NOW)


def test_client_change_deadline() -> None:
    pending = requested()
    # Неподтверждённую заявку можно отозвать до самого начала.
    assert pending.cancel_by_client(START - timedelta(minutes=1))
    assert not pending.cancel_by_client(START)

    confirmed = requested()
    confirmed.confirm(NOW)
    deadline = START - timedelta(hours=12)
    with pytest.raises(ChangeDeadlinePassed):
        confirmed.ensure_changeable(deadline)
    confirmed.ensure_changeable(deadline - timedelta(seconds=1))
    assert confirmed.cancel_by_client(deadline - timedelta(seconds=1))
    with pytest.raises(AppointmentClosed):
        confirmed.ensure_changeable(NOW)


def test_supersede_releases_open_appointment_once() -> None:
    appointment = requested()
    appointment.confirm(NOW)
    assert appointment.supersede(NOW)
    assert not appointment.supersede(NOW)
    assert appointment.cancel_reason is CancelReason.RESCHEDULED
    assert appointment.snapshot()["cancelled_by"] == "client"


def test_masked_phone_for_foreign_numbers() -> None:
    client = ClientSnapshot.new_client("+998901234567", 2)
    assert client.phone_masked == "+99890 ••• 45 67"
    assert client.display_name == "Новый клиент · …45 67"


def test_master_cancels_request_or_confirmed_appointment() -> None:
    """Мастер отменяет заявку или подтверждённую запись — даже после дедлайна клиента."""
    appointment = requested()
    appointment.confirm(NOW)
    appointment.pull_events()
    late = START - timedelta(hours=1)  # клиенту менять уже поздно, мастеру — можно
    assert appointment.cancel_by_master(late) is True
    assert (appointment.cancelled_by, appointment.cancel_reason) == (
        CancelledBy.MASTER,
        CancelReason.MASTER_CANCELLED,
    )
    (event,) = appointment.pull_events()
    assert isinstance(event, AppointmentCancelled)
    assert (event.reason, event.offer_alternatives) == ("master_cancelled", True)
    assert appointment.cancel_by_master(late) is False  # повтор — no-op

    pending = requested()
    assert pending.cancel_by_master(NOW, offer_alternatives=False) is True
    assert pending.pull_events()[-1].offer_alternatives is False  # type: ignore[attr-defined]


def test_master_cannot_cancel_past_visit() -> None:
    """Визит прошёл — отменять нечего."""
    appointment = requested()
    appointment.confirm(NOW)
    with pytest.raises(AppointmentClosed):
        appointment.cancel_by_master(START + timedelta(hours=1))
