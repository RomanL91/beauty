"""Read-модель рассылок (SQL → DTO)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.conversations.application.dto import AnnouncementView, BroadcastView
from beauty.contexts.conversations.application.ports import BroadcastReader
from beauty.contexts.conversations.domain.broadcast import BroadcastStatus
from beauty.contexts.conversations.infrastructure.tables import broadcast_blocks, broadcasts, conversations


class SqlBroadcastReader(BroadcastReader):
    """Рассылки на PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Получить фабрику сессий."""
        self._sessions = session_factory

    async def _views(self, statement: Select[Any], master_id: UUID) -> list[BroadcastView]:
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
            current = 0
            if any(row.status is BroadcastStatus.DRAFT for row in rows):
                count = select(func.count()).where(conversations.c.master_id == master_id)
                current = int((await session.execute(count)).scalar_one())
        return [
            BroadcastView(
                id=row.id,
                text=row.text,
                photo_key=row.photo_key,
                status=row.status.value,
                origin=row.origin.value,
                recipients=current if row.status is BroadcastStatus.DRAFT else row.recipients,
                delivered=row.delivered,
                created_at=row.created_at,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )
            for row in rows
        ]

    async def broadcasts(self, master_id: UUID, limit: int) -> list[BroadcastView]:
        """Свежие сверху."""
        statement = (
            select(broadcasts)
            .where(broadcasts.c.master_id == master_id)
            .order_by(broadcasts.c.created_at.desc(), broadcasts.c.id.desc())
            .limit(limit)
        )
        return await self._views(statement, master_id)

    async def broadcast(self, master_id: UUID, broadcast_id: UUID) -> BroadcastView | None:
        """Своя рассылка."""
        statement = select(broadcasts).where(
            broadcasts.c.id == broadcast_id, broadcasts.c.master_id == master_id
        )
        found = await self._views(statement, master_id)
        return found[0] if found else None

    async def last_started(self, master_id: UUID) -> datetime | None:
        """Последнее начало отправки."""
        statement = select(func.max(broadcasts.c.started_at)).where(broadcasts.c.master_id == master_id)
        async with self._sessions() as session:
            found: datetime | None = (await session.execute(statement)).scalar_one()
        return found

    async def blocked(self, master_id: UUID) -> bool:
        """Есть ли запрет."""
        statement = select(broadcast_blocks.c.master_id).where(broadcast_blocks.c.master_id == master_id)
        async with self._sessions() as session:
            return (await session.execute(statement)).first() is not None

    async def announcements(self, master_id: UUID, since: datetime) -> list[AnnouncementView]:
        """Отправленные с ``since``."""
        statement = (
            select(broadcasts.c.started_at, broadcasts.c.text, broadcasts.c.photo_key)
            .where(
                broadcasts.c.master_id == master_id,
                broadcasts.c.started_at.is_not(None),
                broadcasts.c.started_at >= since,
            )
            .order_by(broadcasts.c.started_at.desc())
            .limit(5)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [AnnouncementView(row.started_at, row.text, row.photo_key is not None) for row in rows]
