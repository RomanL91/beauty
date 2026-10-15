"""Внутрипроцессная шина realtime-событий (Observer)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class Subscription:
    """Подписка на топик: ограниченная очередь сообщений.

    Медленный клиент не должен раздувать память процесса: при переполнении
    отбрасывается самое старое сообщение (для статусов важно последнее).
    """

    def __init__(self, topic: str, capacity: int) -> None:
        """Создать подписку."""
        self.topic = topic
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=capacity)

    def push(self, message: dict[str, Any]) -> None:
        """Положить сообщение без ожидания (вызывается из event loop)."""
        if self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait(message)

    async def next(self, timeout: float) -> dict[str, Any] | None:
        """Дождаться сообщения не дольше ``timeout``; ``None`` — по таймауту."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except TimeoutError:
            return None


class RealtimeHub:
    """Раздаёт сообщения подписчикам топика в пределах процесса."""

    def __init__(self, capacity: int = 16) -> None:
        """Задать ёмкость очереди подписчика."""
        self._capacity = capacity
        self._subscribers: defaultdict[str, set[Subscription]] = defaultdict(set)

    @asynccontextmanager
    async def subscribe(self, topic: str) -> AsyncIterator[Subscription]:
        """Подписаться на время контекста (отписка гарантирована в ``finally``)."""
        subscription = Subscription(topic, self._capacity)
        self._subscribers[topic].add(subscription)
        try:
            yield subscription
        finally:
            subscribers = self._subscribers.get(topic)
            if subscribers is not None:
                subscribers.discard(subscription)
                if not subscribers:
                    del self._subscribers[topic]

    def publish(self, topic: str, message: dict[str, Any]) -> int:
        """Разослать сообщение подписчикам; вернуть их число."""
        subscribers = tuple(self._subscribers.get(topic, ()))
        for subscription in subscribers:
            subscription.push(message)
        return len(subscribers)
