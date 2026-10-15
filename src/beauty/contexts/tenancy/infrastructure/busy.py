"""Источник занятого времени до появления контекста записи."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from beauty.contexts.tenancy.application.ports import BusyTimeSource
from beauty.contexts.tenancy.domain.slots import TimeInterval


class NoBusyTime(BusyTimeSource):
    """Записей ещё нет — мастер свободен в рабочие часы.

    Контекст записи заменит его адаптером, читающим записи и заявки с удержанием.
    """

    async def busy(self, master_id: UUID, start: datetime, end: datetime) -> list[TimeInterval]:
        """Пустой список."""
        return []
