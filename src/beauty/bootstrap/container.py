"""Контейнер приложения (Pure DI без фреймворка).

Зависимости создаются лениво (``cached_property``) и живут столько же, сколько
процесс. Короткоживущие объекты (Unit of Work, обработчики) создают фабрики модулей
на каждый вызов. Каждый процесс (API, бот, relay, планировщик) строит свой
контейнер и берёт из него только нужное — бот, например, не открывает
соединение с RabbitMQ.
"""

from __future__ import annotations

from functools import cached_property

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from beauty.contexts.identity.module import IdentityDependencies, IdentityModule
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.middleware import ConcurrencyRetryMiddleware, LoggingMiddleware
from beauty.shared.domain.clock import Clock, SystemClock
from beauty.shared.domain.ids import IdGenerator, default_id_generator
from beauty.shared.infrastructure.config import Settings
from beauty.shared.infrastructure.db.engine import DatabaseEngineFactory
from beauty.shared.infrastructure.db.scope import TransactionScope
from beauty.shared.infrastructure.messaging.codec import EnvelopeCodec
from beauty.shared.infrastructure.messaging.connection import RabbitConnection
from beauty.shared.infrastructure.messaging.publisher import RabbitEventPublisher
from beauty.shared.infrastructure.messaging.topology import TopologyDeclarer
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.scheduling.registry import JobHandlerRegistry
from beauty.shared.infrastructure.web.errors import HttpErrorMapper


class ApplicationContainer:
    """Общие зависимости процесса и модули контекстов."""

    def __init__(self, settings: Settings, process_name: str = "beauty") -> None:
        """Запомнить настройки и имя процесса."""
        self.settings = settings
        self._process_name = process_name

    @cached_property
    def clock(self) -> Clock:
        """Часы."""
        return SystemClock()

    @cached_property
    def id_generator(self) -> IdGenerator:
        """Генератор UUIDv7."""
        return default_id_generator

    @cached_property
    def engine(self) -> AsyncEngine:
        """Движок БД с пулом соединений."""
        return DatabaseEngineFactory(self.settings.database, self._process_name).create_engine()

    @cached_property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Фабрика сессий."""
        return DatabaseEngineFactory.create_session_factory(self.engine)

    @cached_property
    def transaction_scope(self) -> TransactionScope:
        """Амбиентная транзакция для консьюмеров."""
        return TransactionScope(self.session_factory)

    @cached_property
    def outbox_writer(self) -> OutboxWriter:
        """Писатель outbox."""
        return OutboxWriter()

    @cached_property
    def mediator(self) -> Mediator:
        """Медиатор с зарегистрированными обработчиками всех модулей."""
        mediator = Mediator(middlewares=(LoggingMiddleware(), ConcurrencyRetryMiddleware()))
        self.identity.register(mediator, self.http_errors)
        return mediator

    @cached_property
    def http_errors(self) -> HttpErrorMapper:
        """Маппер ошибок в HTTP."""
        return HttpErrorMapper()

    @cached_property
    def realtime_hub(self) -> RealtimeHub:
        """Хаб realtime-событий процесса."""
        return RealtimeHub()

    @cached_property
    def rabbit(self) -> RabbitConnection:
        """Соединение с RabbitMQ."""
        return RabbitConnection(self.settings.rabbit.url, client_name=self._process_name)

    @cached_property
    def topology(self) -> TopologyDeclarer:
        """Декларатор топологии брокера."""
        return TopologyDeclarer(self.settings.rabbit.events_exchange)

    @cached_property
    def envelope_codec(self) -> EnvelopeCodec:
        """Кодек AMQP-сообщений."""
        return EnvelopeCodec()

    @cached_property
    def event_publisher(self) -> RabbitEventPublisher:
        """Publisher событий с подтверждениями."""
        return RabbitEventPublisher(self.rabbit, self.topology, self.envelope_codec)

    @cached_property
    def job_handlers(self) -> JobHandlerRegistry:
        """Реестр обработчиков отложенных задач (контексты добавят свои)."""
        return JobHandlerRegistry()

    @cached_property
    def identity(self) -> IdentityModule:
        """Модуль Identity."""
        return IdentityModule(
            IdentityDependencies(
                session_factory=self.session_factory,
                outbox_writer=self.outbox_writer,
                clock=self.clock,
                id_generator=self.id_generator,
                hub=self.realtime_hub,
                auth=self.settings.auth,
                telegram=self.settings.telegram,
                http=self.settings.http,
            )
        )

    async def aclose(self) -> None:
        """Закрыть внешние ресурсы, которые успели открыться."""
        if "rabbit" in self.__dict__:
            await self.rabbit.close()
        if "engine" in self.__dict__:
            await self.engine.dispose()
