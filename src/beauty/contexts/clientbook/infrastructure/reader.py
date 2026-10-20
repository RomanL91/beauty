"""Read-модель Clientbook: список и карточки клиентов мастера (только чтение, SQL).

Клиент мастера — строка переписки (Conversations); визиты — записи Booking; имя и
заметки — карточка Clientbook. Список — сводка, а не агрегаты, поэтому читается одним
запросом напрямую из таблиц контекстов, как отчёты админ-панели.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.clientbook.application.dto import (
    ClientCardView,
    ClientPage,
    ClientRow,
    ClientVisit,
    NoteView,
)
from beauty.contexts.clientbook.application.ports import ClientbookReader

HISTORY_LIMIT = 30

_ROWS = """
WITH stats AS (
    SELECT a.client_id,
           count(*) FILTER (WHERE a.status = 'completed') AS visits,
           count(*) FILTER (WHERE a.status = 'cancelled') AS cancelled,
           max(a.start_at) FILTER (WHERE a.status = 'completed') AS last_visit_at,
           min(a.start_at) FILTER (WHERE a.status IN ('requested', 'confirmed') AND a.start_at > :now)
               AS next_visit_at
      FROM booking.appointments a
     WHERE a.master_id = :master
     GROUP BY a.client_id
)
SELECT c.client_id, c.id AS conversation_id, c.created_at AS since,
       coalesce(f.name, 'Новый клиент · …' || right(c.client_phone_masked, 5)) AS display_name,
       f.name IS NOT NULL AS named,
       c.client_phone_masked AS phone_masked,
       coalesce(s.visits, 0) AS visits,
       coalesce(s.cancelled, 0) AS cancelled,
       s.last_visit_at, s.next_visit_at,
       (SELECT count(*) FROM clientbook.notes n WHERE n.file_id = f.id) AS notes,
       greatest(c.created_at, c.last_message_at, s.last_visit_at) AS last_activity_at,
       count(*) OVER () AS total
  FROM conversations.conversations c
  LEFT JOIN stats s ON s.client_id = c.client_id
  LEFT JOIN clientbook.files f ON f.master_id = c.master_id AND f.client_id = c.client_id
 WHERE c.master_id = :master {where}
 ORDER BY last_activity_at DESC, c.id
 LIMIT :limit OFFSET :offset
"""

_VISITS = """
SELECT a.id, a.status, a.start_at, a.end_at, a.service_title, a.service_price_amount, a.cancelled_by
  FROM booking.appointments a
 WHERE a.master_id = :master AND a.client_id = :client
"""

_NOTES = """
SELECT n.id, n.text, n.author, n.created_at
  FROM clientbook.notes n
  JOIN clientbook.files f ON f.id = n.file_id
 WHERE f.master_id = :master AND f.client_id = :client
 ORDER BY n.created_at DESC, n.id
"""


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _row(row: Any) -> ClientRow:
    return ClientRow(
        client_id=row.client_id,
        conversation_id=row.conversation_id,
        display_name=row.display_name,
        named=row.named,
        phone_masked=row.phone_masked,
        visits=row.visits,
        last_visit_at=row.last_visit_at,
        next_visit_at=row.next_visit_at,
        notes=row.notes,
        last_activity_at=row.last_activity_at,
    )


def _visit(row: Any) -> ClientVisit:
    return ClientVisit(
        id=row.id,
        status=row.status,
        start=row.start_at,
        end=row.end_at,
        service_title=row.service_title,
        price_amount=row.service_price_amount,
        cancelled_by=row.cancelled_by,
    )


class SqlClientbookReader(ClientbookReader):
    """Список и карточки на PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Получить фабрику сессий."""
        self._sessions = session_factory

    async def _all(self, sql: str, **params: Any) -> list[Any]:
        async with self._sessions() as session:
            return list((await session.execute(text(sql), params)).all())

    async def page(
        self, master_id: UUID, query: str | None, upcoming_only: bool, limit: int, offset: int, now: datetime
    ) -> ClientPage:
        """Страница списка."""
        conditions: list[str] = []
        params: dict[str, Any] = {"master": master_id, "now": now, "limit": limit, "offset": offset}
        if query:
            match = ["f.name ILIKE :like"]
            params["like"] = _like(query)
            digits = re.sub(r"\D", "", query)
            if digits:
                match.append("regexp_replace(c.client_phone_masked, '\\D', '', 'g') LIKE :digits")
                params["digits"] = f"%{digits}%"
            conditions.append(f"({' OR '.join(match)})")
        if upcoming_only:
            conditions.append("s.next_visit_at IS NOT NULL")
        where = "".join(f" AND {condition}" for condition in conditions)
        rows = await self._all(_ROWS.format(where=where), **params)
        return ClientPage(tuple(_row(r) for r in rows), rows[0].total if rows else 0)

    async def card(self, master_id: UUID, client_id: UUID, now: datetime) -> ClientCardView | None:
        """Карточка: сводка, будущие и прошедшие визиты, заметки."""
        params = {"master": master_id, "client": client_id, "now": now}
        rows = await self._all(_ROWS.format(where=" AND c.client_id = :client"), limit=1, offset=0, **params)
        if not rows:
            return None
        upcoming = await self._all(
            _VISITS + " AND a.status IN ('requested', 'confirmed') AND a.start_at > :now ORDER BY a.start_at",
            **params,
        )
        history = await self._all(
            _VISITS
            + " AND NOT (a.status IN ('requested', 'confirmed') AND a.start_at > :now)"
            + " ORDER BY a.start_at DESC LIMIT :limit",
            limit=HISTORY_LIMIT,
            **params,
        )
        row = rows[0]
        return ClientCardView(
            row=_row(row),
            since=row.since,
            cancelled=row.cancelled,
            upcoming=tuple(_visit(v) for v in upcoming),
            history=tuple(_visit(v) for v in history),
            notes=tuple(await self.notes(master_id, client_id)),
        )

    async def notes(self, master_id: UUID, client_id: UUID) -> list[NoteView]:
        """Заметки, свежие сверху."""
        rows = await self._all(_NOTES, master=master_id, client=client_id)
        return [NoteView(r.id, r.text, r.author, r.created_at) for r in rows]

    async def name(self, master_id: UUID, client_id: UUID) -> str | None:
        """Имя у мастера."""
        rows = await self._all(
            "SELECT name FROM clientbook.files WHERE master_id = :master AND client_id = :client",
            master=master_id,
            client=client_id,
        )
        return rows[0].name if rows else None
