"""Журнал ходов агента: итог и длительность каждого хода (для отчётов хозяина сервиса)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from beauty.contexts.agent.domain.ticket import AgentFace
from beauty.shared.domain.aggregate import AggregateRoot


class AgentRun(AggregateRoot):
    """Ход агента: тикет хода, роль, мастер, итог (``completed`` или статус сбоя), секунды."""

    id: str  # type: ignore[assignment]  # id тикета хода

    def __init__(
        self,
        ticket_id: str,
        master_id: UUID,
        face: AgentFace,
        conversation_id: UUID | None,
        status: str,
        seconds: float,
        created_at: datetime,
    ) -> None:
        """Записать ход."""
        self.id = ticket_id
        self.master_id = master_id
        self.face = face
        self.conversation_id = conversation_id
        self.status = status
        self.seconds = round(seconds, 3)
        self.created_at = created_at

    @property
    def failed(self) -> bool:
        """Ход без ответа модели."""
        return self.status != "completed"
