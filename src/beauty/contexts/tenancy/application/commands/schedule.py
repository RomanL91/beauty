"""Рабочие часы, правила записи и выходные даты."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, time
from uuid import UUID

from beauty.contexts.tenancy.application.commands.base import load_master
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.domain.value_objects import BookingRules, WeeklySchedule, WorkingHours
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class SetWeeklySchedule(Command[None]):
    """Задать рабочие часы: день недели (0 — пн) → интервалы ``(начало, конец)``."""

    master_id: UUID
    days: Mapping[int, tuple[tuple[time, time], ...]] = field(default_factory=dict)


class SetWeeklyScheduleHandler(Handler[SetWeeklySchedule, None]):
    """Заменяет недельное расписание."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: SetWeeklySchedule) -> None:
        """Применить расписание."""
        schedule = WeeklySchedule(
            {
                weekday: tuple(WorkingHours(start, end) for start, end in intervals)
                for weekday, intervals in message.days.items()
            }
        )
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            master.set_schedule(schedule, self._clock.now())
            await uow.commit()


@dataclass(frozen=True, slots=True)
class SetBookingRules(Command[None]):
    """Задать правила записи."""

    master_id: UUID
    confirm_within_hours: int
    change_deadline_hours: int
    min_notice_minutes: int
    horizon_days: int
    slot_step_minutes: int


class SetBookingRulesHandler(Handler[SetBookingRules, None]):
    """Заменяет правила записи."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: SetBookingRules) -> None:
        """Применить правила."""
        rules = BookingRules(
            confirm_within_hours=message.confirm_within_hours,
            change_deadline_hours=message.change_deadline_hours,
            min_notice_minutes=message.min_notice_minutes,
            horizon_days=message.horizon_days,
            slot_step_minutes=message.slot_step_minutes,
        )
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            master.set_booking_rules(rules, self._clock.now())
            await uow.commit()


@dataclass(frozen=True, slots=True)
class SetDaysOff(Command[None]):
    """Задать выходные даты (прошедшие отбрасываются)."""

    master_id: UUID
    days: tuple[date, ...]


class SetDaysOffHandler(Handler[SetDaysOff, None]):
    """Заменяет выходные даты; «сегодня» — по часовому поясу мастера."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: SetDaysOff) -> None:
        """Применить выходные."""
        now = self._clock.now()
        async with self._uow as uow:
            master = await load_master(uow, message.master_id)
            today = now.astimezone(master.timezone.zone()).date()
            master.set_days_off(message.days, today, now)
            await uow.commit()
