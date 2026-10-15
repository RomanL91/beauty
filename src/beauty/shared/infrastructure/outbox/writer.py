"""Запись событий в outbox внутри текущей транзакции."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from beauty.shared.domain.events import DomainEvent
from beauty.shared.infrastructure.outbox.serializer import EventSerializer
from beauty.shared.infrastructure.outbox.table import outbox_table


class OutboxWriter:
    """Пишет события пачкой одним ``INSERT … VALUES (…), (…)``.

    SQLAlchemy 2.0 с asyncpg использует «insertmanyvalues»: N событий — один
    round-trip, а не N. Триггер на таблице выполняет ``pg_notify`` (FOR EACH
    STATEMENT), и relay просыпается сразу после COMMIT, а не по таймеру.
    """

    def __init__(self, serializer: EventSerializer | None = None) -> None:
        """Использовать сериализатор событий."""
        self._serializer = serializer or EventSerializer()

    async def write(self, session: AsyncSession, events: Sequence[DomainEvent]) -> None:
        """Добавить события в outbox (пустой список — без запроса)."""
        if not events:
            return
        rows = []
        for event in events:
            envelope = self._serializer.to_envelope(event)
            rows.append(
                {
                    "id": envelope.message_id,
                    "routing_key": envelope.routing_key,
                    "event_type": envelope.event_type,
                    "event_version": envelope.event_version,
                    "payload": envelope.payload,
                    "occurred_at": envelope.occurred_at,
                }
            )
        await session.execute(insert(outbox_table), rows)
