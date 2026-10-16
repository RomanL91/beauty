"""Порты прикладного слоя Booking.

Расписание и правила записи принадлежат Tenancy, контакты клиентов — Identity;
Booking видит их через узкие порты, адаптеры подключает корень композиции.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from beauty.contexts.booking.domain.value_objects import ServiceSnapshot


@dataclass(frozen=True, slots=True)
class BookableSlot:
    """Проверенное свободное окно и правила мастера на момент заявки."""

    service: ServiceSnapshot
    start: datetime
    end: datetime
    timezone: str
    confirm_within: timedelta
    change_deadline_hours: int


class SlotPolicy(ABC):
    """Проверка окна по расписанию, правилам и занятости мастера."""

    @abstractmethod
    async def check(self, master_id: UUID, service_id: UUID, start: datetime) -> BookableSlot:
        """Окно или ``SlotUnavailableError``."""


class ClientDirectory(ABC):
    """Контакты клиентов."""

    @abstractmethod
    async def phone(self, client_id: UUID) -> str:
        """Телефон клиента в E.164."""


class AppointmentTimers(ABC):
    """Отложенные действия над записью (задачи планировщика в той же транзакции)."""

    @abstractmethod
    async def expire_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Отклонить заявку, если мастер не ответит до ``moment``."""

    @abstractmethod
    async def complete_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Отметить визит состоявшимся в ``moment``."""

    @abstractmethod
    async def cancel(self, appointment_id: UUID) -> None:
        """Отменить все ожидающие задачи записи."""


@dataclass(frozen=True, slots=True)
class BusyInterval:
    """Занятое время мастера."""

    start: datetime
    end: datetime


class BusyTimeReader(ABC):
    """Занятые интервалы мастера (SQL → DTO)."""

    @abstractmethod
    async def read(self, master_id: UUID, start: datetime, end: datetime) -> list[BusyInterval]:
        """Заявки и записи, пересекающие ``[start, end)``."""
