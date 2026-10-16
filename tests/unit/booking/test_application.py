"""Прикладной слой Booking на in-memory двойниках."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from beauty.contexts.booking.application.commands import (
    CancelAppointment,
    CancelAppointmentHandler,
    CompleteAppointment,
    CompleteAppointmentHandler,
    ConfirmAppointment,
    ConfirmAppointmentHandler,
    DeclineAppointment,
    DeclineAppointmentHandler,
    ExpireAppointment,
    ExpireAppointmentHandler,
    RequestAppointment,
    RequestAppointmentHandler,
    RescheduleAppointment,
    RescheduleAppointmentHandler,
)
from beauty.contexts.booking.application.errors import (
    AppointmentNotFoundError,
    SlotTakenError,
    SlotUnavailableError,
)
from beauty.contexts.booking.domain.errors import ChangeDeadlinePassed
from beauty.contexts.booking.domain.events import AppointmentRequested
from beauty.contexts.booking.domain.value_objects import AppointmentStatus, CancelReason
from beauty.shared.domain.ids import UuidV7Generator
from tests.fakes import FrozenClock
from tests.unit.booking.fakes import BookingStore, InMemoryBookingUnitOfWork, OpenSlots, Phones

MASTER = UUID(int=100)
CLIENT = UUID(int=200)
STRANGER = UUID(int=300)
START = datetime(2026, 10, 17, 5, 0, tzinfo=UTC)


class World:
    """Хранилище, часы и фабрики обработчиков."""

    def __init__(self, clock: FrozenClock) -> None:
        """Пустой мир."""
        self.store = BookingStore()
        self.clock = clock
        self.slots = OpenSlots()
        self.ids = UuidV7Generator()

    def uow(self) -> InMemoryBookingUnitOfWork:
        """Новый Unit of Work."""
        return InMemoryBookingUnitOfWork(self.store)

    async def request(self, start: datetime = START, client: UUID = CLIENT) -> UUID:
        """Заявка; вернуть id."""
        handler = RequestAppointmentHandler(self.uow(), self.slots, Phones(), self.clock, self.ids)
        payload = await handler.handle(RequestAppointment(MASTER, client, UUID(int=7), start))
        return UUID(payload["id"])

    async def reschedule(self, appointment_id: UUID, start: datetime, client: UUID = CLIENT) -> UUID:
        """Перенос; вернуть id новой заявки."""
        handler = RescheduleAppointmentHandler(self.uow(), self.slots, Phones(), self.clock, self.ids)
        payload = await handler.handle(RescheduleAppointment(appointment_id, client, start))
        return UUID(payload["id"])

    async def confirm(self, appointment_id: UUID) -> None:
        """Подтвердить."""
        await ConfirmAppointmentHandler(self.uow(), self.clock).handle(ConfirmAppointment(appointment_id))

    def status(self, appointment_id: UUID) -> AppointmentStatus:
        """Текущий статус."""
        return self.store.appointments[appointment_id].status


@pytest.fixture
def world(clock: FrozenClock) -> World:
    """Чт 15 окт 2026, 12:00 UTC."""
    return World(clock)


async def test_request_schedules_expiry_and_counts_visits(world: World) -> None:
    first = await world.request()
    assert world.store.timers == {f"expire:{first}": world.clock.now() + timedelta(hours=2)}
    await world.confirm(first)
    assert world.store.timers == {
        f"complete:{first}": START + timedelta(hours=1),
        f"remind:{first}": START - timedelta(hours=24),
    }

    second = await world.request(START + timedelta(days=1))
    assert world.store.appointments[second].client.visit_number == 2
    requested = [e for e in world.store.events if isinstance(e, AppointmentRequested)]
    assert [e.appointment_id for e in requested] == [first, second]


async def test_busy_and_unavailable_slots(world: World) -> None:
    await world.request()
    with pytest.raises(SlotTakenError):
        await world.request(START + timedelta(minutes=30), client=STRANGER)
    world.slots.closed.add(START + timedelta(hours=3))
    with pytest.raises(SlotUnavailableError):
        await world.request(START + timedelta(hours=3))


async def test_expire_and_decline(world: World) -> None:
    expiring = await world.request()
    await ExpireAppointmentHandler(world.uow(), world.clock).handle(ExpireAppointment(expiring))
    assert world.status(expiring) is AppointmentStatus.REQUESTED  # ещё рано
    world.clock.advance(timedelta(hours=2))
    await ExpireAppointmentHandler(world.uow(), world.clock).handle(ExpireAppointment(expiring))
    assert world.store.appointments[expiring].cancel_reason is CancelReason.EXPIRED

    declined = await world.request()  # окно освободилось
    payload = await DeclineAppointmentHandler(world.uow(), world.clock).handle(DeclineAppointment(declined))
    assert payload["cancelled_by"] == "master"
    # Таймер истёкшей заявки выполнен планировщиком (в двойнике остаётся), отклонённой — снят.
    assert set(world.store.timers) == {f"expire:{expiring}"}


async def test_client_cancels_only_own_appointment(world: World) -> None:
    appointment = await world.request()
    cancel = CancelAppointmentHandler(world.uow(), world.clock)
    with pytest.raises(AppointmentNotFoundError):
        await cancel.handle(CancelAppointment(appointment, STRANGER))
    payload = await CancelAppointmentHandler(world.uow(), world.clock).handle(
        CancelAppointment(appointment, CLIENT)
    )
    assert payload["status"] == "cancelled"
    assert payload["cancelled_by"] == "client"
    assert world.store.timers == {}


async def test_reschedule_keeps_old_until_confirmed(world: World) -> None:
    old = await world.request()
    await world.confirm(old)
    first_try = await world.reschedule(old, START + timedelta(days=1))
    second_try = await world.reschedule(old, START + timedelta(days=2))
    # Предыдущий перенос отозван, старая запись в силе.
    assert world.status(first_try) is AppointmentStatus.CANCELLED
    assert world.status(old) is AppointmentStatus.CONFIRMED
    assert world.store.appointments[second_try].reschedule_of == old

    await world.confirm(second_try)
    assert world.store.appointments[old].cancel_reason is CancelReason.RESCHEDULED
    assert set(world.store.timers) == {f"complete:{second_try}", f"remind:{second_try}"}


async def test_declined_reschedule_leaves_old_and_overlap_is_taken(world: World) -> None:
    old = await world.request()
    await world.confirm(old)
    with pytest.raises(SlotTakenError):
        await world.reschedule(old, START + timedelta(minutes=30))
    moved = await world.reschedule(old, START + timedelta(days=1))
    await DeclineAppointmentHandler(world.uow(), world.clock).handle(DeclineAppointment(moved))
    assert world.status(old) is AppointmentStatus.CONFIRMED


async def test_reschedule_after_deadline_and_completion(world: World) -> None:
    appointment = await world.request()
    await world.confirm(appointment)
    world.clock.moment = START - timedelta(hours=11)
    with pytest.raises(ChangeDeadlinePassed):
        await world.reschedule(appointment, START + timedelta(days=1))
    world.clock.moment = START + timedelta(hours=1)
    await CompleteAppointmentHandler(world.uow(), world.clock).handle(CompleteAppointment(appointment))
    assert world.status(appointment) is AppointmentStatus.COMPLETED
