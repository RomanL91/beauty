"""SSE-поток статуса входа."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

from beauty.contexts.identity.application.queries import GetChallengeStatus
from beauty.contexts.identity.infrastructure.realtime import ChallengeTopic
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.web.sse import ServerSentEvent

FINAL_STATUSES = frozenset({"completed", "consumed", "rejected", "expired"})


class ChallengeStatusStream:
    """Поток изменений статуса входа до финального состояния.

    Подписка на хаб оформляется до первого чтения статуса — иначе событие,
    пришедшее между чтением и подпиской, потерялось бы. Если realtime-событие
    всё-таки не дошло (брокер недоступен, процесс перезапущен), раз в
    ``poll_interval`` статус перечитывается из БД: поток самовосстанавливается.
    Поток ограничен по времени, и закрывается при отключении клиента.
    """

    def __init__(
        self,
        mediator: Mediator,
        hub: RealtimeHub,
        challenge_id: UUID,
        browser_secret: str,
        is_disconnected: Callable[[], Awaitable[bool]],
        poll_interval: float = 5.0,
        max_duration: float = 330.0,
    ) -> None:
        """Собрать поток."""
        self._mediator = mediator
        self._hub = hub
        self._challenge_id = challenge_id
        self._browser_secret = browser_secret
        self._is_disconnected = is_disconnected
        self._poll_interval = poll_interval
        self._max_duration = max_duration

    async def events(self) -> AsyncIterator[bytes]:
        """Генератор кадров SSE."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._max_duration
        async with self._hub.subscribe(ChallengeTopic.for_challenge(self._challenge_id)) as subscription:
            status = await self._read_status()
            yield self._frame(status, retry_ms=3000)
            while status not in FINAL_STATUSES and loop.time() < deadline:
                if await self._is_disconnected():
                    return
                message = await subscription.next(self._poll_interval)
                fresh = str(message["status"]) if message is not None else await self._read_status()
                if fresh != status:
                    status = fresh
                    yield self._frame(status)
                else:
                    yield ServerSentEvent.heartbeat()

    async def _read_status(self) -> str:
        """Перечитать статус через query."""
        view = await self._mediator.send(GetChallengeStatus(self._challenge_id, self._browser_secret))
        return view.status

    def _frame(self, status: str, retry_ms: int | None = None) -> bytes:
        """Кадр с новым статусом."""
        return ServerSentEvent(data={"status": status}, event="status", retry_ms=retry_ms).encode()
