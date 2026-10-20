"""Порты прикладного слоя Booking.

Расписание и правила записи принадлежат Tenancy, контакты клиентов — Identity;
Booking видит их через узкие порты, адаптеры подключает корень композиции.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from beauty.contexts.booking.application.schedule import DayAppointment, WorkingCalendar
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

    @abstractmethod
    async def name(self, master_id: UUID, client_id: UUID) -> str | None:
        """Имя клиента в картотеке мастера (``None`` — не задано)."""


class AppointmentTimers(ABC):
    """Отложенные действия над записью (задачи планировщика в той же транзакции)."""

    @abstractmethod
    async def expire_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Отклонить заявку, если мастер не ответит до ``moment``."""

    @abstractmethod
    async def complete_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Отметить визит состоявшимся в ``moment``."""

    @abstractmethod
    async def remind_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Напомнить клиенту о визите в ``moment``."""

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


class CalendarSource(ABC):
    """Рабочие часы и выходные мастера (Tenancy)."""

    @abstractmethod
    async def calendar(self, master_id: UUID, start: date, days: int) -> WorkingCalendar:
        """Дни подряд с ``start``."""


class ConversationDirectory(ABC):
    """Переписки мастера с клиентами (Conversations)."""

    @abstractmethod
    async def conversation_ids(self, master_id: UUID, client_ids: Collection[UUID]) -> dict[UUID, UUID]:
        """Клиент → id переписки (у кого она есть)."""


class ClientAppointmentsReader(ABC):
    """Записи клиента к мастеру (SQL)."""

    @abstractmethod
    async def upcoming(self, master_id: UUID, client_id: UUID, now: datetime) -> list[DayAppointment]:
        """Открытые заявки и записи, которые ещё не начались."""


class MasterDayReader(ABC):
    """Записи мастера за период (SQL)."""

    @abstractmethod
    async def appointments(self, master_id: UUID, start: datetime, end: datetime) -> list[DayAppointment]:
        """Заявки, подтверждённые и состоявшиеся записи, начинающиеся в ``[start, end)``."""
