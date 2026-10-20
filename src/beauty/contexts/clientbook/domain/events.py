"""Доменные события Clientbook."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.shared.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ClientRenamed(DomainEvent):
    """Мастер (или агент по поручению) дал клиенту имя; ``None`` — вернул подпись по телефону.

    Подписчики — Conversations (подпись в переписке) и Booking (открытые заявки и записи).
    """

    routing_key = "clientbook.client.renamed"

    master_id: UUID
    client_id: UUID
    name: str | None
