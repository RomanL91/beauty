"""Таймеры записи — задачи ``infra.scheduled_jobs`` в транзакции Unit of Work."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from beauty.contexts.booking.application.ports import AppointmentTimers
from beauty.shared.infrastructure.scheduling.scheduler import JobRequest, JobScheduler


class ScheduledAppointmentTimers(AppointmentTimers):
    """Ключи задач: ``booking:<id>:expire``, ``booking:<id>:complete``, ``booking:<id>:remind``."""

    EXPIRE_KIND: ClassVar[str] = "booking.expire_request"
    COMPLETE_KIND: ClassVar[str] = "booking.complete_visit"
    REMIND_KIND: ClassVar[str] = "booking.remind_visit"

    def __init__(self, scheduler: JobScheduler) -> None:
        """Привязать к планировщику сессии."""
        self._scheduler = scheduler

    async def expire_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Автоотклонение заявки."""
        await self._schedule(self.EXPIRE_KIND, appointment_id, "expire", moment)

    async def complete_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Отметка о визите."""
        await self._schedule(self.COMPLETE_KIND, appointment_id, "complete", moment)

    async def remind_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Напоминание о визите."""
        await self._schedule(self.REMIND_KIND, appointment_id, "remind", moment)

    async def cancel(self, appointment_id: UUID) -> None:
        """Снять все ожидающие задачи записи."""
        await self._scheduler.cancel_by_prefix(f"booking:{appointment_id}:")

    async def _schedule(self, kind: str, appointment_id: UUID, suffix: str, moment: datetime) -> None:
        await self._scheduler.schedule(
            JobRequest(
                kind=kind,
                dedup_key=f"booking:{appointment_id}:{suffix}",
                due_at=moment,
                payload={"appointment_id": str(appointment_id)},
            )
        )
