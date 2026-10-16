"""Тикет запуска агента — права одного хода.

По итогам спайка тикет — короткий непрозрачный id: длинный подписанный тикет модель
переписывала с ошибками. Всё содержимое (мастер, роль, переписка, клиент, срок) хранит
бэкенд; MCP-сервер сверяет мастера тикета с мастером токена профиля.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from beauty.contexts.agent.domain.errors import InvalidTicket
from beauty.shared.domain.aggregate import AggregateRoot

_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"  # без похожих 0/o, 1/l/i
_LENGTH = 8


class AgentFace(StrEnum):
    """Роль агента в ходе."""

    FRONT_DESK = "front_desk"


class RunTicket(AggregateRoot):
    """Права хода: с кем агент говорит и от чьего имени действует."""

    id: str  # type: ignore[assignment]  # короткий строковый id вместо UUID

    def __init__(
        self,
        ticket_id: str,
        master_id: UUID,
        face: AgentFace,
        conversation_id: UUID,
        client_id: UUID,
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        """Создать тикет (используйте ``issue``)."""
        self.id = ticket_id
        self.master_id = master_id
        self.face = face
        self.conversation_id = conversation_id
        self.client_id = client_id
        self.expires_at = expires_at
        self.handed_off = False
        self.created_at = created_at

    @classmethod
    def issue(
        cls,
        *,
        master_id: UUID,
        conversation_id: UUID,
        client_id: UUID,
        now: datetime,
        ttl: timedelta,
    ) -> RunTicket:
        """Новый тикет ресепшна: ``t-`` и 8 символов (≈ 40 бит случайности)."""
        ticket_id = "t-" + "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
        return cls(ticket_id, master_id, AgentFace.FRONT_DESK, conversation_id, client_id, now + ttl, now)

    def check(self, master_id: UUID, face: AgentFace, now: datetime) -> None:
        """Тикет годится этому мастеру и этой роли сейчас."""
        if self.master_id != master_id or self.face is not face or now >= self.expires_at:
            raise InvalidTicket()

    def hand_off(self) -> None:
        """Агент передал диалог мастеру в этом ходе."""
        self.handed_off = True
