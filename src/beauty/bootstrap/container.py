"""Контейнер приложения (Pure DI без фреймворка).

Зависимости создаются лениво (``cached_property``) и живут столько же, сколько
процесс. Короткоживущие объекты (Unit of Work, обработчики) создают фабрики модулей
на каждый вызов. Каждый процесс (API, бот, relay, планировщик) строит свой
контейнер и берёт из него только нужное — бот, например, не открывает
соединение с RabbitMQ.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from beauty.bootstrap.adapters import (
    AgentBooking,
    AgentCabinet,
    AgentConversations,
    AgentMasters,
    BookedTime,
    BookingFrontDesk,
    ConversationsDirectory,
    IdentityClientDirectory,
    OwnedMasters,
    TenancyCalendar,
    TenancyMasterCatalog,
    TenancySlotPolicy,
)
from beauty.contexts.agent.application.ports import AgentRuntime
from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.contexts.agent.infrastructure.hermes import CommandRunner, HermesProvisioner, ProfileFiles
from beauty.contexts.agent.infrastructure.runtime import DisabledRuntime, HermesRuntime
from beauty.contexts.agent.module import AgentDependencies, AgentModule
from beauty.contexts.booking.module import BookingDependencies, BookingModule
from beauty.contexts.conversations.module import ConversationsDependencies, ConversationsModule
from beauty.contexts.identity.module import IdentityDependencies, IdentityModule
from beauty.contexts.tenancy.module import TenancyDependencies, TenancyModule
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
from beauty.shared.infrastructure.messaging.subscription import EventSubscription
from beauty.shared.infrastructure.messaging.topology import TopologyDeclarer
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.realtime.bridge import TopicResolver
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.scheduling.registry import JobHandlerRegistry
from beauty.shared.infrastructure.scheduling.scheduler import JobRequest
from beauty.shared.infrastructure.storage.local import LocalFileStorage
from beauty.shared.infrastructure.storage.signing import SignedMediaUrls
from beauty.shared.infrastructure.web.auth import BearerAuth, MasterAuth
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
        self.tenancy.register(mediator, self.http_errors)
        self.booking.register(mediator, self.http_errors)
        self.conversations.register(mediator, self.http_errors)
        self.agent.register(mediator, self.http_errors)
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
        """Реестр обработчиков отложенных задач всех контекстов."""
        registry = JobHandlerRegistry()
        self.booking.register_jobs(registry, self.mediator)
        self.conversations.register_jobs(registry)
        return registry

    def startup_jobs(self) -> tuple[JobRequest, ...]:
        """Периодические задачи, которые планировщик ставит при старте."""
        return self.conversations.startup_jobs()

    def event_subscriptions(self) -> tuple[EventSubscription, ...]:
        """Консьюмеры интеграционных событий всех контекстов."""
        return (*self.conversations.subscriptions(self.mediator), *self.agent.subscriptions(self.mediator))

    def realtime_resolvers(self) -> tuple[TopicResolver, ...]:
        """Realtime-топики всех контекстов (для моста в процессе API)."""
        return (
            *self.identity.realtime_resolvers(),
            *self.conversations.realtime_resolvers(),
            *self.agent.topic_resolvers(),
        )

    @cached_property
    def file_storage(self) -> LocalFileStorage:
        """Файловое хранилище (голосовые)."""
        return LocalFileStorage(self.settings.storage.root, self.id_generator)

    @cached_property
    def media_urls(self) -> SignedMediaUrls:
        """Подписанные ссылки на файлы."""
        return SignedMediaUrls(
            self.settings.auth.jwt_secret.get_secret_value(), self.settings.http.api_prefix, self.clock
        )

    @cached_property
    def client_auth(self) -> BearerAuth:
        """Аутентификация клиента по access-токену Identity."""
        verifier = self.identity.access_token_verifier
        return BearerAuth(lambda token: verifier.verify(token).account_id)

    @cached_property
    def master_auth(self) -> MasterAuth:
        """Аутентификация мастера: учётная запись владельца страницы."""
        return MasterAuth(self.client_auth, OwnedMasters(lambda: self.mediator))

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

    @cached_property
    def tenancy(self) -> TenancyModule:
        """Модуль Tenancy."""
        return TenancyModule(
            TenancyDependencies(
                session_factory=self.session_factory,
                outbox_writer=self.outbox_writer,
                clock=self.clock,
                id_generator=self.id_generator,
                busy_time=BookedTime(lambda: self.mediator),
            )
        )

    @cached_property
    def booking(self) -> BookingModule:
        """Модуль Booking."""
        return BookingModule(
            BookingDependencies(
                session_factory=self.session_factory,
                outbox_writer=self.outbox_writer,
                clock=self.clock,
                id_generator=self.id_generator,
                slot_policy=TenancySlotPolicy(lambda: self.mediator),
                clients=IdentityClientDirectory(lambda: self.mediator),
                calendar=TenancyCalendar(lambda: self.mediator),
                conversations=ConversationsDirectory(lambda: self.mediator),
            )
        )

    @cached_property
    def conversations(self) -> ConversationsModule:
        """Модуль Conversations."""
        return ConversationsModule(
            ConversationsDependencies(
                session_factory=self.session_factory,
                outbox_writer=self.outbox_writer,
                clock=self.clock,
                id_generator=self.id_generator,
                hub=self.realtime_hub,
                storage=self.file_storage,
                media=self.media_urls,
                catalog=TenancyMasterCatalog(lambda: self.mediator),
                booking=BookingFrontDesk(lambda: self.mediator),
                contacts=IdentityClientDirectory(lambda: self.mediator),
                poll_interval=self.settings.http.sse_poll_interval,
                stream_max_duration=self.settings.http.sse_max_duration,
            )
        )

    @cached_property
    def agent_http(self) -> httpx.AsyncClient:
        """HTTP-клиент к Hermes."""
        return httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))

    @cached_property
    def agent_runtime(self) -> AgentRuntime:
        """Hermes или выключенный runtime (``BEAUTY_AGENT__RUNTIME``)."""
        settings = self.settings.agent
        if settings.runtime == "hermes":
            return HermesRuntime(settings.hermes_url, self.agent_http, timeout=settings.run_timeout)
        return DisabledRuntime()

    @cached_property
    def hermes_runner(self) -> CommandRunner:
        """Hermes CLI."""
        return CommandRunner.from_string(self.settings.agent.hermes_cmd)

    @cached_property
    def hermes_files(self) -> ProfileFiles:
        """Файлы профилей Hermes."""
        settings = self.settings.agent
        owner = None
        if settings.profiles_owner:
            uid, gid = settings.profiles_owner.split(":")
            owner = (int(uid), int(gid))
        return ProfileFiles(Path(settings.profiles_root), owner)

    @cached_property
    def agent(self) -> AgentModule:
        """Модуль Agent."""
        settings = self.settings.agent
        provisioner = HermesProvisioner(
            self.hermes_runner,
            self.hermes_files,
            {
                AgentFace.FRONT_DESK: settings.template_profile,
                AgentFace.BACK_OFFICE: settings.office_template_profile,
            },
        )
        return AgentModule(
            AgentDependencies(
                session_factory=self.session_factory,
                outbox_writer=self.outbox_writer,
                clock=self.clock,
                runtime=self.agent_runtime,
                provisioner=provisioner,
                masters=AgentMasters(lambda: self.mediator),
                conversations=AgentConversations(lambda: self.mediator),
                booking=AgentBooking(lambda: self.mediator),
                cabinet=AgentCabinet(lambda: self.mediator),
                ids=self.id_generator,
                storage=self.file_storage,
                media=self.media_urls,
                ticket_ttl=settings.ticket_ttl,
            )
        )

    async def aclose(self) -> None:
        """Закрыть внешние ресурсы, которые успели открыться."""
        if "agent_http" in self.__dict__:
            await self.agent_http.aclose()
        if "rabbit" in self.__dict__:
            await self.rabbit.close()
        if "engine" in self.__dict__:
            await self.engine.dispose()
