"""SSE-поток ленты переписки."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

from beauty.contexts.conversations.application.dto import FeedRead
from beauty.contexts.conversations.application.queries import ReadFeed
from beauty.contexts.conversations.infrastructure.realtime import FeedTopic
from beauty.contexts.conversations.presentation.api.render import MessageRenderer
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.web.sse import ServerSentEvent

RETRY_FRAME = b"retry: 3000\n\n"


class ConversationFeedStream:
    """Поток событий ленты с досылкой по ``Last-Event-ID``.

    Подписка на хаб оформляется до первого чтения журнала, поэтому событие между
    чтением и подпиской не теряется. Realtime-сообщение лишь будит поток — сами
    события читаются из журнала после последнего отправленного номера (с проверкой
    доступа), так что дубли и пропуски исключены. Без моста поток опрашивает журнал
    раз в ``poll_interval``. Поток ограничен по времени: клиент переподключится с
    ``Last-Event-ID`` и ничего не потеряет.
    """

    def __init__(
        self,
        mediator: Mediator,
        hub: RealtimeHub,
        renderer: MessageRenderer,
        conversation_id: UUID,
        client_id: UUID,
        after: int | None,
        is_disconnected: Callable[[], Awaitable[bool]],
        poll_interval: float = 5.0,
        max_duration: float = 600.0,
    ) -> None:
        """Собрать поток; ``after`` — ``Last-Event-ID`` клиента (``None`` — только новое)."""
        self._mediator = mediator
        self._hub = hub
        self._renderer = renderer
        self._conversation_id = conversation_id
        self._client_id = client_id
        self._after = after
        self._is_disconnected = is_disconnected
        self._poll_interval = poll_interval
        self._max_duration = max_duration

    async def events(self) -> AsyncIterator[bytes]:
        """Генератор кадров."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._max_duration
        async with self._hub.subscribe(FeedTopic.of(self._conversation_id)) as subscription:
            yield RETRY_FRAME
            position = await self._read(self._after)
            if position.reset:
                yield ServerSentEvent(
                    {"type": "reset"}, event="reset", event_id=str(position.last_seq)
                ).encode()
            else:
                for frame in self._frames(position):
                    yield frame
            last = position.last_seq
            while loop.time() < deadline:
                if await self._is_disconnected():
                    return
                woke = await subscription.next(self._poll_interval)
                fresh = await self._read(last)
                if fresh.reset:
                    yield ServerSentEvent(
                        {"type": "reset"}, event="reset", event_id=str(fresh.last_seq)
                    ).encode()
                elif fresh.entries:
                    for frame in self._frames(fresh):
                        yield frame
                elif woke is None:
                    yield ServerSentEvent.heartbeat()
                last = fresh.last_seq

    async def _read(self, after: int | None) -> FeedRead:
        return await self._mediator.send(ReadFeed(self._conversation_id, self._client_id, after=after))

    def _frames(self, feed: FeedRead) -> list[bytes]:
        return [
            ServerSentEvent(
                {"type": entry.change, "message": self._renderer.render(entry.message)},
                event=entry.change,
                event_id=str(entry.seq),
            ).encode()
            for entry in feed.entries
        ]
