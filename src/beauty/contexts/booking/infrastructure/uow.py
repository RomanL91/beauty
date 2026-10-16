"""Unit of Work Booking на SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.booking.application.errors import SlotTakenError
from beauty.contexts.booking.application.uow import BookingUnitOfWork
from beauty.contexts.booking.infrastructure.repositories import SqlAlchemyAppointmentRepository
from beauty.contexts.booking.infrastructure.tables import NO_OVERLAP_CONSTRAINT
from beauty.contexts.booking.infrastructure.timers import ScheduledAppointmentTimers
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.db.errors import EXCLUSION_VIOLATION, DatabaseErrorTranslator
from beauty.shared.infrastructure.db.tracker import AggregateTracker
from beauty.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.scheduling.scheduler import JobScheduler


class BookingErrorTranslator(DatabaseErrorTranslator):
    """Нарушение «одно время — одна запись» → ``SlotTakenError`` (бизнес-конфликт)."""

    def translate(self, error: Exception) -> Exception:
        """Перевести ошибку БД."""
        if (
            isinstance(error, IntegrityError)
            and self.sqlstate(error) == EXCLUSION_VIOLATION
            and self.constraint_name(error) == NO_OVERLAP_CONSTRAINT
        ):
            return SlotTakenError()
        return super().translate(error)


class SqlAlchemyBookingUnitOfWork(SqlAlchemyUnitOfWork, BookingUnitOfWork):
    """Репозиторий записей и таймеры поверх сессии единицы работы."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        outbox_writer: OutboxWriter,
        id_generator: IdGenerator,
    ) -> None:
        """Получить зависимости."""
        super().__init__(session_factory, outbox_writer, BookingErrorTranslator())
        self._id_generator = id_generator

    def _create_repositories(self, session: AsyncSession, tracker: AggregateTracker) -> None:
        """Инициализировать репозиторий и таймеры."""
        self.appointments = SqlAlchemyAppointmentRepository(session, tracker)
        self.timers = ScheduledAppointmentTimers(JobScheduler(session, self._id_generator))
