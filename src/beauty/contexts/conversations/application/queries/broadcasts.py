"""Запросы рассылок: список и рассылка для кабинета, недавние объявления для агента."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from beauty.contexts.conversations.application.dto import AnnouncementView, BroadcastsView, BroadcastView
from beauty.contexts.conversations.application.errors import BroadcastNotFoundError
from beauty.contexts.conversations.application.ports import BroadcastReader
from beauty.contexts.conversations.domain.broadcast import next_allowed
from beauty.shared.application.cqrs import Handler, Query
from beauty.shared.domain.clock import Clock

LIST_LIMIT = 30


@dataclass(frozen=True, slots=True)
class ListBroadcasts(Query[BroadcastsView]):
    """Рассылки мастера, разрешены ли и когда можно следующую."""

    master_id: UUID


class ListBroadcastsHandler(Handler[ListBroadcasts, BroadcastsView]):
    """Список из read-модели."""

    def __init__(self, reader: BroadcastReader, clock: Clock) -> None:
        """Получить read-модель и часы."""
        self._reader = reader
        self._clock = clock

    async def handle(self, message: ListBroadcasts) -> BroadcastsView:
        """Список."""
        reader, master_id = self._reader, message.master_id
        return BroadcastsView(
            items=tuple(await reader.broadcasts(master_id, LIST_LIMIT)),
            allowed=not await reader.blocked(master_id),
            next_at=next_allowed(await reader.last_started(master_id), self._clock.now()),
        )


@dataclass(frozen=True, slots=True)
class GetBroadcast(Query[BroadcastView]):
    """Рассылка своего мастера."""

    master_id: UUID
    broadcast_id: UUID


class GetBroadcastHandler(Handler[GetBroadcast, BroadcastView]):
    """Рассылка или ``broadcast_not_found``."""

    def __init__(self, reader: BroadcastReader) -> None:
        """Получить read-модель."""
        self._reader = reader

    async def handle(self, message: GetBroadcast) -> BroadcastView:
        """Рассылка."""
        found = await self._reader.broadcast(message.master_id, message.broadcast_id)
        if found is None:
            raise BroadcastNotFoundError()
        return found


@dataclass(frozen=True, slots=True)
class RecentAnnouncements(Query[list[AnnouncementView]]):
    """Объявления мастера за последние ``days`` дней (агент ресепшна знает, о чём писали клиентам)."""

    master_id: UUID
    days: int = 30


class RecentAnnouncementsHandler(Handler[RecentAnnouncements, list[AnnouncementView]]):
    """Отправленные, свежие сверху."""

    def __init__(self, reader: BroadcastReader, clock: Clock) -> None:
        """Получить read-модель и часы."""
        self._reader = reader
        self._clock = clock

    async def handle(self, message: RecentAnnouncements) -> list[AnnouncementView]:
        """Объявления."""
        since = self._clock.now() - timedelta(days=message.days)
        return await self._reader.announcements(message.master_id, since)
