"""Планирование и отмена задач внутри транзакции вызывающего кода."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from beauty.shared.domain.ids import IdGenerator, default_id_generator
from beauty.shared.infrastructure.outbox.serializer import JsonValueConverter
from beauty.shared.infrastructure.scheduling.table import JobStatus, scheduled_jobs_table


@dataclass(frozen=True, slots=True)
class JobRequest:
    """Запрос на планирование задачи.

    ``dedup_key`` — бизнес-ключ (например, ``reminder:<appointment_id>:24h``):
    повторное планирование с тем же ключом переносит существующую задачу.
    """

    kind: str
    dedup_key: str
    due_at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)


class JobScheduler:
    """Пишет задачи в ``infra.scheduled_jobs`` через сессию текущего Unit of Work."""

    def __init__(
        self,
        session: AsyncSession,
        id_generator: IdGenerator = default_id_generator,
        converter: JsonValueConverter | None = None,
    ) -> None:
        """Привязать планировщик к сессии."""
        self._session = session
        self._id_generator = id_generator
        self._converter = converter or JsonValueConverter()

    async def schedule(self, request: JobRequest) -> None:
        """Создать задачу или перенести существующую с тем же ключом.

        Выполняющуюся задачу (``running``) не трогаем: перезапись привела бы к
        двойному выполнению.
        """
        table = scheduled_jobs_table
        payload = self._converter.convert(dict(request.payload))
        statement = insert(table).values(
            id=self._id_generator.new(),
            kind=request.kind,
            dedup_key=request.dedup_key,
            payload=payload,
            due_at=request.due_at,
            status=JobStatus.PENDING.value,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.dedup_key],
            set_={
                "kind": statement.excluded.kind,
                "payload": statement.excluded.payload,
                "due_at": statement.excluded.due_at,
                "status": JobStatus.PENDING.value,
                "attempts": 0,
                "last_error": None,
                "locked_until": None,
                "updated_at": func.now(),
            },
            where=table.c.status != JobStatus.RUNNING.value,
        )
        await self._session.execute(statement)

    async def cancel(self, dedup_key: str) -> None:
        """Отменить ожидающую задачу по ключу."""
        await self._session.execute(
            update(scheduled_jobs_table)
            .where(
                scheduled_jobs_table.c.dedup_key == dedup_key,
                scheduled_jobs_table.c.status == JobStatus.PENDING.value,
            )
            .values(status=JobStatus.CANCELLED.value)
        )

    async def cancel_by_prefix(self, prefix: str) -> None:
        """Отменить все ожидающие задачи с ключом, начинающимся на ``prefix``."""
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        await self._session.execute(
            update(scheduled_jobs_table)
            .where(
                scheduled_jobs_table.c.dedup_key.like(f"{escaped}%", escape="\\"),
                scheduled_jobs_table.c.status == JobStatus.PENDING.value,
            )
            .values(status=JobStatus.CANCELLED.value)
        )
