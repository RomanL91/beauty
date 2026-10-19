"""Журнал действий администраторов: кто, что, над чем, когда."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from beauty.shared.domain.aggregate import AggregateRoot


class AuditEntry(AggregateRoot):
    """Запись журнала (неизменяемая)."""

    def __init__(
        self,
        entry_id: UUID,
        admin_id: UUID,
        admin_login: str,
        action: str,
        target: str | None,
        summary: str,
        created_at: datetime,
    ) -> None:
        """Записать действие."""
        self.id = entry_id
        self.admin_id = admin_id
        self.admin_login = admin_login
        self.action = action
        self.target = target
        self.summary = summary
        self.created_at = created_at
