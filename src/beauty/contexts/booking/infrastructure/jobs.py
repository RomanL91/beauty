"""Обработчики задач планировщика Booking."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar
from uuid import UUID

from beauty.contexts.booking.application.commands import CompleteAppointment, ExpireAppointment
from beauty.contexts.booking.infrastructure.timers import ScheduledAppointmentTimers
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.scheduling.registry import JobHandler


class ExpireRequestJob(JobHandler):
    """Мастер не ответил вовремя — отклонить заявку."""

    kind: ClassVar[str] = ScheduledAppointmentTimers.EXPIRE_KIND

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, payload: Mapping[str, Any]) -> None:
        """Отправить команду (она идемпотентна)."""
        await self._mediator.send(ExpireAppointment(UUID(str(payload["appointment_id"]))))


class CompleteVisitJob(JobHandler):
    """Время визита прошло — отметить запись состоявшейся."""

    kind: ClassVar[str] = ScheduledAppointmentTimers.COMPLETE_KIND

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, payload: Mapping[str, Any]) -> None:
        """Отправить команду (она идемпотентна)."""
        await self._mediator.send(CompleteAppointment(UUID(str(payload["appointment_id"]))))
