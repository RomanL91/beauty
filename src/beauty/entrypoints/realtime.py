"""Фоновый сервис realtime-моста в процессе API."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from beauty.shared.infrastructure.messaging.codec import EnvelopeCodec
from beauty.shared.infrastructure.messaging.connection import RabbitConnection
from beauty.shared.infrastructure.messaging.consumer import RabbitConsumer
from beauty.shared.infrastructure.messaging.topology import ConsumerQueueSpec, TopologyDeclarer
from beauty.shared.infrastructure.realtime.bridge import RealtimeBridge

logger = logging.getLogger(__name__)


class RealtimeBridgeService:
    """Подключает эксклюзивную очередь экземпляра API к ``RealtimeHub``.

    Запуск — в фоновой задаче с повторами: если брокер недоступен при старте, API
    всё равно поднимается, а SSE работает на опросе БД, пока мост не подключится.
    """

    def __init__(
        self,
        connection: RabbitConnection,
        topology: TopologyDeclarer,
        codec: EnvelopeCodec,
        bridge: RealtimeBridge,
        retry_delay: float = 5.0,
    ) -> None:
        """Собрать сервис."""
        self._consumer = RabbitConsumer(
            connection,
            topology,
            ConsumerQueueSpec(name="realtime", binding_keys=bridge.binding_keys, transient=True),
            bridge,
            codec,
            prefetch=256,
        )
        self._retry_delay = retry_delay
        self._task: asyncio.Task[None] | None = None
        self._started = False

    def start(self) -> None:
        """Запустить подключение в фоне."""
        self._task = asyncio.create_task(self._connect_forever(), name="realtime-bridge")

    async def stop(self) -> None:
        """Остановить консьюмер и фоновую задачу."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._started:
            await self._consumer.stop(timeout=5.0)

    async def _connect_forever(self) -> None:
        """Повторять подключение до успеха."""
        while not self._started:
            try:
                await self._consumer.start()
                self._started = True
            except Exception:
                logger.warning("Realtime-мост: брокер недоступен, повтор через %.0f с", self._retry_delay)
                await asyncio.sleep(self._retry_delay)
