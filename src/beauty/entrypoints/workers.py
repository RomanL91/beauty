"""Долгоживущие процессы: бот, outbox relay, планировщик задач, консьюмеры событий, MCP."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from beauty.bootstrap.container import ApplicationContainer
from beauty.shared.infrastructure.inbox.guard import (
    InboxClaimFirstHandler,
    InboxGuard,
    InboxIdempotentHandler,
)
from beauty.shared.infrastructure.messaging.consumer import RabbitConsumer
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.messaging.subscription import EventSubscription
from beauty.shared.infrastructure.outbox.listener import PostgresNotificationListener
from beauty.shared.infrastructure.outbox.relay import OutboxRelay
from beauty.shared.infrastructure.outbox.table import OUTBOX_NOTIFY_CHANNEL
from beauty.shared.infrastructure.scheduling.poller import ScheduledJobPoller
from beauty.shared.infrastructure.scheduling.scheduler import JobScheduler

logger = logging.getLogger(__name__)


class Worker(ABC):
    """Процесс, работающий до сигнала остановки."""

    def __init__(self, container: ApplicationContainer) -> None:
        """Получить контейнер."""
        self._container = container

    @abstractmethod
    async def run(self, stop: asyncio.Event) -> None:
        """Работать, пока не выставлен ``stop``."""


class TelegramBotWorker(Worker):
    """Long polling бота авторизации."""

    async def run(self, stop: asyncio.Event) -> None:
        """Поллить Telegram до остановки."""
        container = self._container
        bot = Bot(
            token=container.settings.telegram.bot_token.get_secret_value(),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dispatcher = Dispatcher()
        dispatcher.include_router(container.identity.bot_router(container.mediator))
        polling = asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False), name="bot-polling")
        try:
            await stop.wait()
            await dispatcher.stop_polling()
            with contextlib.suppress(asyncio.CancelledError):
                await polling
        finally:
            await bot.session.close()
            await container.aclose()


class OutboxRelayWorker(Worker):
    """Перенос событий из outbox в RabbitMQ."""

    async def run(self, stop: asyncio.Event) -> None:
        """Слушать NOTIFY и публиковать пачки."""
        container = self._container
        settings = container.settings
        listener = PostgresNotificationListener(settings.database.url, OUTBOX_NOTIFY_CHANNEL)
        relay = OutboxRelay(
            container.session_factory,
            container.event_publisher,
            listener,
            container.clock,
            batch_size=settings.outbox.batch_size,
            idle_poll_interval=settings.outbox.idle_poll_interval,
        )
        await listener.start()
        try:
            await relay.run(stop)
        finally:
            await listener.stop()
            await container.aclose()


class SchedulerWorker(Worker):
    """Выполнение отложенных задач."""

    async def run(self, stop: asyncio.Event) -> None:
        """Опрашивать ``infra.scheduled_jobs``."""
        container = self._container
        settings = container.settings.scheduler
        poller = ScheduledJobPoller(
            container.session_factory,
            container.job_handlers,
            container.clock,
            batch_size=settings.batch_size,
            poll_interval=settings.poll_interval,
            max_attempts=settings.max_attempts,
        )
        try:
            await self._ensure_startup_jobs()
            await poller.run(stop)
        finally:
            await container.aclose()

    async def _ensure_startup_jobs(self) -> None:
        """Поставить периодические задачи (повторная постановка идемпотентна)."""
        container = self._container
        async with container.session_factory() as session, session.begin():
            scheduler = JobScheduler(session, container.id_generator)
            for request in container.startup_jobs():
                await scheduler.schedule(request)


class EventConsumersWorker(Worker):
    """Консьюмеры интеграционных событий контекстов (inbox, повторы, DLQ)."""

    async def run(self, stop: asyncio.Event) -> None:
        """Потреблять очереди до остановки."""
        container = self._container
        guard = InboxGuard()
        consumers = [
            RabbitConsumer(
                container.rabbit,
                container.topology,
                subscription.spec,
                self._guarded(subscription, guard),
                container.envelope_codec,
                prefetch=container.settings.rabbit.prefetch,
            )
            for subscription in container.event_subscriptions()
        ]
        try:
            for consumer in consumers:
                await consumer.start()
            await stop.wait()
        finally:
            for consumer in consumers:
                await consumer.stop()
            await container.aclose()

    def _guarded(self, subscription: EventSubscription, guard: InboxGuard) -> IntegrationEventHandler:
        """Обработчик с inbox: в общей транзакции или с отметкой до обработки."""
        name = subscription.spec.name
        if subscription.ambient_transaction:
            return InboxIdempotentHandler(
                subscription.handler, self._container.transaction_scope, guard, name
            )
        return InboxClaimFirstHandler(subscription.handler, self._container.session_factory, guard, name)


class McpServerWorker(Worker):
    """MCP-сервер ``beauty-tools`` для Hermes (Streamable HTTP: ``/mcp`` и ``/office/mcp``)."""

    async def run(self, stop: asyncio.Event) -> None:
        """Обслуживать MCP до остановки."""
        container = self._container
        settings = container.settings.agent
        app = container.agent.mcp_application(settings.mcp_host)
        server = uvicorn.Server(
            uvicorn.Config(app, host=settings.mcp_host, port=settings.mcp_port, log_config=None)
        )
        serving = asyncio.create_task(server.serve(), name="mcp")
        stopping = asyncio.create_task(stop.wait(), name="stop-signal")
        try:
            done, _ = await asyncio.wait({serving, stopping}, return_when=asyncio.FIRST_COMPLETED)
            if stopping in done:
                server.should_exit = True
            else:
                stopping.cancel()
            await serving
        finally:
            await container.aclose()
