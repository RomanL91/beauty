"""Порты прикладного слоя Clientbook.

Клиент мастера — тот, у кого есть с ним переписка (Conversations). Список и карточка —
read-модель поверх переписок, записей (Booking) и карточек: только чтение.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from beauty.contexts.clientbook.application.dto import ClientCardView, ClientPage, NoteView


class Roster(ABC):
    """Клиенты мастера (Conversations)."""

    @abstractmethod
    async def has_client(self, master_id: UUID, client_id: UUID) -> bool:
        """Есть ли у мастера переписка с клиентом."""


class ClientbookReader(ABC):
    """Список и карточки клиентов (SQL)."""

    @abstractmethod
    async def page(
        self, master_id: UUID, query: str | None, upcoming_only: bool, limit: int, offset: int, now: datetime
    ) -> ClientPage:
        """Страница списка: свежие по активности сверху."""

    @abstractmethod
    async def card(self, master_id: UUID, client_id: UUID, now: datetime) -> ClientCardView | None:
        """Карточка (``None`` — нет такого клиента)."""

    @abstractmethod
    async def notes(self, master_id: UUID, client_id: UUID) -> list[NoteView]:
        """Заметки о клиенте, свежие сверху."""

    @abstractmethod
    async def name(self, master_id: UUID, client_id: UUID) -> str | None:
        """Имя клиента у мастера (``None`` — не задано)."""
