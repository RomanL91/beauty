"""Заявка на запись и перенос."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.contexts.booking.application.commands.base import (
    AppointmentPayload,
    load,
    withdraw_reschedules,
)
from beauty.contexts.booking.application.ports import BookableSlot, ClientDirectory, SlotPolicy
from beauty.contexts.booking.application.uow import BookingUnitOfWork
from beauty.contexts.booking.domain.appointment import Appointment
from beauty.contexts.booking.domain.value_objects import ClientSnapshot, TimeSlot
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


class _Requester:
    """Создание заявки: окно проверяет Tenancy, «не занято» окончательно — БД."""

    def __init__(
        self,
        uow: BookingUnitOfWork,
        slots: SlotPolicy,
        clients: ClientDirectory,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._slots = slots
        self._clients = clients
        self._clock = clock
        self._ids = ids

    async def _create(
        self, master_id: UUID, client_id: UUID, slot: BookableSlot, reschedule_of: UUID | None
    ) -> Appointment:
        """Создать заявку внутри открытого Unit of Work."""
        uow = self._uow
        phone = await self._clients.phone(client_id)
        visits = await uow.appointments.visits_before(master_id, client_id, slot.start)
        appointment = Appointment.request(
            appointment_id=self._ids.new(),
            master_id=master_id,
            client_id=client_id,
            service=slot.service,
            client=ClientSnapshot.new_client(phone, visits + 1),
            slot=TimeSlot(slot.start, slot.end),
            timezone=slot.timezone,
            confirm_within=slot.confirm_within,
            change_deadline_hours=slot.change_deadline_hours,
            now=self._clock.now(),
            reschedule_of=reschedule_of,
        )
        uow.appointments.add(appointment)
        await uow.timers.expire_at(appointment.id, appointment.hold_until)
        return appointment


@dataclass(frozen=True, slots=True)
class RequestAppointment(Command[AppointmentPayload]):
    """Клиент просит записать его на услугу к ``start``."""

    master_id: UUID
    client_id: UUID
    service_id: UUID
    start: datetime


class RequestAppointmentHandler(_Requester, Handler[RequestAppointment, AppointmentPayload]):
    """Заявка; занятое окно — ``SlotUnavailableError`` / ``SlotTakenError``."""

    async def handle(self, message: RequestAppointment) -> AppointmentPayload:
        """Создать заявку."""
        slot = await self._slots.check(message.master_id, message.service_id, message.start)
        async with self._uow as uow:
            appointment = await self._create(message.master_id, message.client_id, slot, None)
            await uow.commit()
        return appointment.snapshot()


@dataclass(frozen=True, slots=True)
class RescheduleAppointment(Command[AppointmentPayload]):
    """Клиент переносит запись на ``start``: новая заявка, старая — до её подтверждения."""

    appointment_id: UUID
    client_id: UUID
    start: datetime


class RescheduleAppointmentHandler(_Requester, Handler[RescheduleAppointment, AppointmentPayload]):
    """Перенос: предыдущие неподтверждённые переносы этой записи отзываются."""

    async def handle(self, message: RescheduleAppointment) -> AppointmentPayload:
        """Создать заявку на перенос."""
        async with self._uow as uow:
            current = await load(uow, message.appointment_id, message.client_id)
            now = self._clock.now()
            current.ensure_changeable(now)
            slot = await self._slots.check(current.master_id, current.service.service_id, message.start)
            await withdraw_reschedules(uow, current, now)
            appointment = await self._create(current.master_id, current.client_id, slot, current.id)
            await uow.commit()
        return appointment.snapshot()
