"""SSE-поток кабинета мастера (``/me/events``)."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.application.errors import ConversationNotFoundError
from beauty.contexts.conversations.application.queries import GetConversationSummary, GetMasterMessage
from beauty.contexts.conversations.presentation.api.render import MessageRenderer, render_summary
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.realtime.cabinet import FRAME_SIGNAL, MasterTopic
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.web.sse import ServerSentEvent

RETRY_FRAME = b"retry: 3000\n\n"


class MasterEventsStream:
    """Живой поток кабинета: без журнала.

    События приходят с момента подключения. Переподключение с ``Last-Event-ID``
    сразу получает ``event: reset`` — кабинет перечитывает график и чаты (они читаются
    целиком), поэтому пропущенное за время обрыва не теряется. Realtime-сообщение
    несёт только ссылку: сообщение и сводку поток читает запросами мастера.
    """

    def __init__(
        self,
        mediator: Mediator,
        hub: RealtimeHub,
        renderer: MessageRenderer,
        master_id: UUID,
        resumed: bool,
        is_disconnected: Callable[[], Awaitable[bool]],
        ping_interval: float = 15.0,
        max_duration: float = 600.0,
    ) -> None:
        """Собрать поток; ``resumed`` — клиент прислал ``Last-Event-ID``."""
        self._mediator = mediator
        self._hub = hub
        self._renderer = renderer
        self._master_id = master_id
        self._resumed = resumed
        self._is_disconnected = is_disconnected
        self._ping_interval = ping_interval
        self._max_duration = max_duration

    async def events(self) -> AsyncIterator[bytes]:
        """Генератор кадров."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._max_duration
        numbers = itertools.count(1)
        async with self._hub.subscribe(MasterTopic.of(self._master_id)) as subscription:
            yield RETRY_FRAME
            if self._resumed:
                yield ServerSentEvent({"type": "reset"}, event="reset", event_id=str(next(numbers))).encode()
            while loop.time() < deadline:
                if await self._is_disconnected():
                    return
                signal = await subscription.next(min(self._ping_interval, max(deadline - loop.time(), 0.01)))
                if signal is None:
                    yield ServerSentEvent.heartbeat()
                    continue
                frame = await self._frame(signal)
                if frame is not None:
                    event, data = frame
                    yield ServerSentEvent(data, event=event, event_id=str(next(numbers))).encode()

    async def _frame(self, signal: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        kind = signal.get("kind")
        if kind == FRAME_SIGNAL:  # готовый кадр другого контекста (лента поручений)
            return str(signal["event"]), dict(signal["data"])
        if kind == "appointment":
            return "appointment.updated", {
                "type": "appointment.updated",
                "appointment": signal["appointment"],
            }
        if kind == "conversation":
            return await self._conversation_frame(UUID(signal["conversation_id"]))
        if kind == "message":
            return await self._message_frame(str(signal["change"]), UUID(signal["message_id"]))
        return None

    async def _conversation_frame(self, conversation_id: UUID) -> tuple[str, dict[str, Any]] | None:
        try:
            summary = await self._mediator.send(GetConversationSummary(self._master_id, conversation_id))
        except ConversationNotFoundError:
            return None
        return "conversation.updated", {
            "type": "conversation.updated",
            "conversation": render_summary(summary),
        }

    async def _message_frame(self, change: str, message_id: UUID) -> tuple[str, dict[str, Any]] | None:
        found = await self._mediator.send(GetMasterMessage(self._master_id, message_id))
        if found is None:
            return None
        conversation_id, message = found
        return change, {
            "type": change,
            "conversation_id": str(conversation_id),
            "message": self._renderer.render(message),
        }
