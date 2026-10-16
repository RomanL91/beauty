"""Модуль контекста Booking."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.booking.application.commands import (
    CancelAppointment,
    CancelAppointmentByMaster,
    CancelAppointmentByMasterHandler,
    CancelAppointmentHandler,
    CompleteAppointment,
    CompleteAppointmentHandler,
    ConfirmAppointment,
    ConfirmAppointmentHandler,
    DeclineAppointment,
    DeclineAppointmentHandler,
    ExpireAppointment,
    ExpireAppointmentHandler,
    RequestAppointment,
    RequestAppointmentHandler,
    RescheduleAppointment,
    RescheduleAppointmentHandler,
)
from beauty.contexts.booking.application.ports import (
    CalendarSource,
    ClientDirectory,
    ConversationDirectory,
    SlotPolicy,
)
from beauty.contexts.booking.application.queries import (
    GetDaySchedule,
    GetDayScheduleHandler,
    ListBusyIntervals,
    ListBusyIntervalsHandler,
    ListClientAppointments,
    ListClientAppointmentsHandler,
)
from beauty.contexts.booking.infrastructure.jobs import CompleteVisitJob, ExpireRequestJob
from beauty.contexts.booking.infrastructure.mapping import BookingOrmMapper
from beauty.contexts.booking.infrastructure.readers import (
    SqlBusyTimeReader,
    SqlClientAppointmentsReader,
    SqlMasterDayReader,
)
from beauty.contexts.booking.infrastructure.uow import SqlAlchemyBookingUnitOfWork
from beauty.contexts.booking.presentation.api.cabinet import cabinet_router
from beauty.contexts.booking.presentation.api.controller import BookingApiController
from beauty.shared.application.mediator import Mediator
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.scheduling.registry import JobHandlerRegistry
from beauty.shared.infrastructure.web.auth import BearerAuth, MasterAuth
from beauty.shared.infrastructure.web.errors import HttpErrorMapper

_HTTP_STATUSES: dict[str, int] = {
    "appointment_not_found": 404,
    "slot_unavailable": 409,
    "slot_taken": 409,
    "appointment_not_pending": 409,
    "request_expired": 409,
    "appointment_closed": 409,
    "change_deadline_passed": 409,
    "invalid_time_slot": 422,
}


@dataclass(frozen=True, slots=True)
class BookingDependencies:
    """Общие зависимости и адаптеры портов к соседним контекстам."""

    session_factory: async_sessionmaker[AsyncSession]
    outbox_writer: OutboxWriter
    clock: Clock
    id_generator: IdGenerator
    slot_policy: SlotPolicy
    clients: ClientDirectory
    calendar: CalendarSource
    conversations: ConversationDirectory


class BookingModule:
    """Сборка контекста Booking."""

    def __init__(self, dependencies: BookingDependencies) -> None:
        """Создать долгоживущие компоненты."""
        BookingOrmMapper.map()
        self._deps = dependencies
        self._busy_reader = SqlBusyTimeReader(dependencies.session_factory)
        self._day_reader = SqlMasterDayReader(dependencies.session_factory)
        self._client_reader = SqlClientAppointmentsReader(dependencies.session_factory)

    def register(self, mediator: Mediator, http_errors: HttpErrorMapper) -> None:
        """Зарегистрировать обработчики и коды ошибок."""
        deps = self._deps
        clock, ids, slots, clients = deps.clock, deps.id_generator, deps.slot_policy, deps.clients
        mediator.register(
            RequestAppointment, lambda: RequestAppointmentHandler(self._uow(), slots, clients, clock, ids)
        )
        mediator.register(
            RescheduleAppointment,
            lambda: RescheduleAppointmentHandler(self._uow(), slots, clients, clock, ids),
        )
        mediator.register(ConfirmAppointment, lambda: ConfirmAppointmentHandler(self._uow(), clock))
        mediator.register(DeclineAppointment, lambda: DeclineAppointmentHandler(self._uow(), clock))
        mediator.register(CancelAppointment, lambda: CancelAppointmentHandler(self._uow(), clock))
        mediator.register(
            CancelAppointmentByMaster, lambda: CancelAppointmentByMasterHandler(self._uow(), clock)
        )
        mediator.register(ExpireAppointment, lambda: ExpireAppointmentHandler(self._uow(), clock))
        mediator.register(CompleteAppointment, lambda: CompleteAppointmentHandler(self._uow(), clock))
        mediator.register(ListBusyIntervals, lambda: ListBusyIntervalsHandler(self._busy_reader))
        mediator.register(
            ListClientAppointments, lambda: ListClientAppointmentsHandler(self._client_reader, clock)
        )
        mediator.register(
            GetDaySchedule,
            lambda: GetDayScheduleHandler(deps.calendar, self._day_reader, deps.conversations),
        )
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def register_jobs(self, registry: JobHandlerRegistry, mediator: Mediator) -> None:
        """Обработчики задач планировщика."""
        registry.register(ExpireRequestJob(mediator))
        registry.register(CompleteVisitJob(mediator))

    def api_router(self, mediator: Mediator, auth: BearerAuth) -> APIRouter:
        """HTTP-роутер записей клиента."""
        return BookingApiController(mediator, auth).router()

    def cabinet_router(self, mediator: Mediator, auth: MasterAuth) -> APIRouter:
        """HTTP-роутер кабинета мастера (график, решения по заявкам)."""
        return cabinet_router(mediator, auth)

    def _uow(self) -> SqlAlchemyBookingUnitOfWork:
        """Новый Unit of Work на каждый обработчик."""
        return SqlAlchemyBookingUnitOfWork(
            self._deps.session_factory, self._deps.outbox_writer, self._deps.id_generator
        )
