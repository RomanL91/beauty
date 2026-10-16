"""Порт репозитория записей."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from beauty.contexts.booking.domain.appointment import Appointment


class AppointmentRepository(ABC):
    """Коллекция записей."""

    @abstractmethod
    def add(self, appointment: Appointment) -> None:
        """Добавить новую запись."""

    @abstractmethod
    async def get(self, appointment_id: UUID) -> Appointment | None:
        """Запись по id."""

    @abstractmethod
    async def pending_reschedules(self, appointment_id: UUID) -> list[Appointment]:
        """Неподтверждённые заявки на перенос этой записи."""

    @abstractmethod
    async def visits_before(self, master_id: UUID, client_id: UUID, moment: datetime) -> int:
        """Сколько подтверждённых и состоявшихся визитов клиента к мастеру до ``moment``."""
