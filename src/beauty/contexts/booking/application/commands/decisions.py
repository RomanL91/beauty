"""Решения по заявке: мастер, клиент, планировщик."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.booking.application.commands.base import (
    AppointmentPayload,
    load,
    withdraw_reschedules,
)
from beauty.contexts.booking.application.uow import BookingUnitOfWork
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


class _Decision:
    """Обработчик решения: Unit of Work и часы."""

    def __init__(self, uow: BookingUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock


@dataclass(frozen=True, slots=True)
class ConfirmAppointment(Command[AppointmentPayload]):
    """Мастер подтверждает заявку."""

    appointment_id: UUID


class ConfirmAppointmentHandler(_Decision, Handler[ConfirmAppointment, AppointmentPayload]):
    """Подтверждение; подтверждённый перенос освобождает прежнюю запись."""

    async def handle(self, message: ConfirmAppointment) -> AppointmentPayload:
        """Подтвердить."""
        async with self._uow as uow:
            appointment = await load(uow, message.appointment_id)
            now = self._clock.now()
            if appointment.confirm(now):
                await uow.timers.cancel(appointment.id)
                await uow.timers.complete_at(appointment.id, appointment.slot.end)
                if appointment.reschedule_of is not None:
                    previous = await uow.appointments.get(appointment.reschedule_of)
                    if previous is not None and previous.supersede(now):
                        await uow.timers.cancel(previous.id)
            await uow.commit()
        return appointment.snapshot()


@dataclass(frozen=True, slots=True)
class DeclineAppointment(Command[AppointmentPayload]):
    """Мастер отклоняет заявку (отклонённый перенос оставляет прежнюю запись в силе)."""

    appointment_id: UUID


class DeclineAppointmentHandler(_Decision, Handler[DeclineAppointment, AppointmentPayload]):
    """Отклонение."""

    async def handle(self, message: DeclineAppointment) -> AppointmentPayload:
        """Отклонить."""
        async with self._uow as uow:
            appointment = await load(uow, message.appointment_id)
            if appointment.decline(self._clock.now()):
                await uow.timers.cancel(appointment.id)
            await uow.commit()
        return appointment.snapshot()


@dataclass(frozen=True, slots=True)
class CancelAppointment(Command[AppointmentPayload]):
    """Клиент отменяет свою заявку или запись."""

    appointment_id: UUID
    client_id: UUID


class CancelAppointmentHandler(_Decision, Handler[CancelAppointment, AppointmentPayload]):
    """Отмена клиентом (вместе с неподтверждёнными переносами)."""

    async def handle(self, message: CancelAppointment) -> AppointmentPayload:
        """Отменить."""
        async with self._uow as uow:
            appointment = await load(uow, message.appointment_id, message.client_id)
            now = self._clock.now()
            if appointment.cancel_by_client(now):
                await uow.timers.cancel(appointment.id)
                await withdraw_reschedules(uow, appointment, now)
            await uow.commit()
        return appointment.snapshot()


@dataclass(frozen=True, slots=True)
class ExpireAppointment(Command[None]):
    """Планировщик: срок ответа мастера истёк."""

    appointment_id: UUID


class ExpireAppointmentHandler(_Decision, Handler[ExpireAppointment, None]):
    """Отклонение системой (идемпотентно: решённая заявка не трогается)."""

    async def handle(self, message: ExpireAppointment) -> None:
        """Отклонить просроченную заявку."""
        async with self._uow as uow:
            appointment = await uow.appointments.get(message.appointment_id)
            if appointment is not None and appointment.expire(self._clock.now()):
                await uow.commit()


@dataclass(frozen=True, slots=True)
class CompleteAppointment(Command[None]):
    """Планировщик: время визита прошло."""

    appointment_id: UUID


class CompleteAppointmentHandler(_Decision, Handler[CompleteAppointment, None]):
    """Отметка «визит состоялся» (идемпотентно)."""

    async def handle(self, message: CompleteAppointment) -> None:
        """Завершить визит."""
        async with self._uow as uow:
            appointment = await uow.appointments.get(message.appointment_id)
            if appointment is not None and appointment.complete(self._clock.now()):
                await uow.commit()
