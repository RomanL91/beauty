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
    BACK_OFFICE = "back_office"


class RunTicket(AggregateRoot):
    """Права хода: с кем агент говорит и от чьего имени действует."""

    id: str  # type: ignore[assignment]  # короткий строковый id вместо UUID

    def __init__(
        self,
        ticket_id: str,
        master_id: UUID,
        face: AgentFace,
        conversation_id: UUID | None,
        client_id: UUID | None,
        expires_at: datetime,
        created_at: datetime,
        catalog: str | None = None,
    ) -> None:
        """Создать тикет (используйте ``issue``).

        ``catalog`` — отпечаток страницы мастера (услуги, цены, правила), которую агент
        видел в инструкциях хода: по нему следующий ход узнаёт, что страница изменилась.
        """
        self.id = ticket_id
        self.master_id = master_id
        self.face = face
        self.conversation_id = conversation_id
        self.client_id = client_id
        self.expires_at = expires_at
        self.handed_off = False
        self.asked_master = False
        self.created_at = created_at
        self.catalog = catalog

    @classmethod
    def issue(
        cls,
        *,
        master_id: UUID,
        conversation_id: UUID,
        client_id: UUID,
        now: datetime,
        ttl: timedelta,
        catalog: str | None = None,
    ) -> RunTicket:
        """Новый тикет ресепшна: ``t-`` и 8 символов (≈ 40 бит случайности)."""
        return cls(
            _new_id(), master_id, AgentFace.FRONT_DESK, conversation_id, client_id, now + ttl, now, catalog
        )

    @classmethod
    def issue_office(
        cls, *, master_id: UUID, now: datetime, ttl: timedelta, catalog: str | None = None
    ) -> RunTicket:
        """Новый тикет кабинета: агент действует от имени мастера, клиента у хода нет."""
        return cls(_new_id(), master_id, AgentFace.BACK_OFFICE, None, None, now + ttl, now, catalog)

    def check(self, master_id: UUID, face: AgentFace, now: datetime) -> None:
        """Тикет годится этому мастеру и этой роли сейчас."""
        if self.master_id != master_id or self.face is not face or now >= self.expires_at:
            raise InvalidTicket()

    def hand_off(self) -> None:
        """Агент передал диалог мастеру в этом ходе."""
        self.handed_off = True

    def ask_master(self) -> None:
        """Агент кабинета задал мастеру вопрос с вариантами: ответ — карточка, не текст хода."""
        self.asked_master = True


def _new_id() -> str:
    return "t-" + "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
