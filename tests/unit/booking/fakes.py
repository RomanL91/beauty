"""In-memory двойники Booking."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from beauty.contexts.booking.application.errors import SlotTakenError, SlotUnavailableError
from beauty.contexts.booking.application.ports import (
    AppointmentTimers,
    BookableSlot,
    ClientDirectory,
    SlotPolicy,
)
from beauty.contexts.booking.application.uow import BookingUnitOfWork
from beauty.contexts.booking.domain.appointment import Appointment
from beauty.contexts.booking.domain.repositories import AppointmentRepository
from beauty.contexts.booking.domain.value_objects import AppointmentStatus, ServiceSnapshot
from beauty.shared.domain.events import DomainEvent
from beauty.shared.infrastructure.db.tracker import AggregateTracker

SERVICE = ServiceSnapshot(UUID(int=7), "Массаж спины", 60, 1_200_000)


class BookingStore:
    """Хранилище, переживающее Unit of Work; таймеры — словарь «ключ → момент»."""

    def __init__(self) -> None:
        """Пусто."""
        self.appointments: dict[UUID, Appointment] = {}
        self.timers: dict[str, datetime] = {}
        self.events: list[DomainEvent] = []


class InMemoryAppointments(AppointmentRepository):
    """Записи в памяти; пересечение открытых записей мастера — как исключающее ограничение."""

    def __init__(self, store: BookingStore, tracker: AggregateTracker) -> None:
        """Связать с хранилищем."""
        self._store, self._tracker = store, tracker
        self.added: list[Appointment] = []

    def add(self, appointment: Appointment) -> None:
        """Добавить (проверка пересечений — при коммите)."""
        self.added.append(self._tracker.track(appointment))

    async def get(self, appointment_id: UUID) -> Appointment | None:
        """По id."""
        found = self._store.appointments.get(appointment_id)
        return None if found is None else self._tracker.track(found)

    async def pending_reschedules(self, appointment_id: UUID) -> list[Appointment]:
        """Открытые заявки на перенос."""
        return [
            self._tracker.track(a)
            for a in self._store.appointments.values()
            if a.reschedule_of == appointment_id and a.status is AppointmentStatus.REQUESTED
        ]

    async def visits_before(self, master_id: UUID, client_id: UUID, moment: datetime) -> int:
        """Подтверждённые и состоявшиеся визиты до момента."""
        return sum(
            1
            for a in self._store.appointments.values()
            if a.master_id == master_id
            and a.client_id == client_id
            and a.slot.start < moment
            and a.status in (AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED)
        )

    def flush(self) -> None:
        """Сохранить добавленные, как БД с ``EXCLUDE``."""
        for new in self.added:
            for other in self._store.appointments.values():
                if (
                    other.is_open
                    and new.is_open
                    and other.master_id == new.master_id
                    and other.slot.start < new.slot.end
                    and new.slot.start < other.slot.end
                ):
                    raise SlotTakenError()
            self._store.appointments[new.id] = new


class RecordingTimers(AppointmentTimers):
    """Таймеры в словаре хранилища."""

    def __init__(self, store: BookingStore) -> None:
        """Связать с хранилищем."""
        self._store = store

    async def expire_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Запомнить."""
        self._store.timers[f"expire:{appointment_id}"] = moment

    async def complete_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Запомнить."""
        self._store.timers[f"complete:{appointment_id}"] = moment

    async def remind_at(self, appointment_id: UUID, moment: datetime) -> None:
        """Запомнить."""
        self._store.timers[f"remind:{appointment_id}"] = moment

    async def cancel(self, appointment_id: UUID) -> None:
        """Забыть все таймеры записи."""
        for key in [k for k in self._store.timers if k.endswith(str(appointment_id))]:
            del self._store.timers[key]


class InMemoryBookingUnitOfWork(BookingUnitOfWork):
    """Коммит переносит новые записи в хранилище и собирает события."""

    def __init__(self, store: BookingStore) -> None:
        """Связать с хранилищем."""
        self._store = store
        self._tracker = AggregateTracker()

    async def _begin(self) -> None:
        self._tracker = AggregateTracker()
        self._repository = InMemoryAppointments(self._store, self._tracker)
        self.appointments = self._repository
        self.timers = RecordingTimers(self._store)

    async def commit(self) -> None:
        """Сохранить."""
        self._repository.flush()
        self._store.events.extend(self._tracker.collect_events())

    async def rollback(self) -> None:
        """Нечего откатывать."""


class OpenSlots(SlotPolicy):
    """Любое время свободно (кроме явно закрытых); услуга — ``SERVICE``."""

    def __init__(self) -> None:
        """Ничего не закрыто."""
        self.closed: set[datetime] = set()

    async def check(self, master_id: UUID, service_id: UUID, start: datetime) -> BookableSlot:
        """Окно на длительность услуги."""
        if start in self.closed:
            raise SlotUnavailableError()
        return BookableSlot(
            service=SERVICE,
            start=start,
            end=start + timedelta(minutes=SERVICE.duration_min),
            timezone="Asia/Almaty",
            confirm_within=timedelta(hours=2),
            change_deadline_hours=12,
        )


class Phones(ClientDirectory):
    """Все клиенты с одним номером."""

    async def phone(self, client_id: UUID) -> str:
        """Телефон."""
        return "+77051238967"
