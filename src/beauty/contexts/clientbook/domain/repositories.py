"""Порты репозиториев Clientbook."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from beauty.contexts.clientbook.domain.client_file import ClientFile


class ClientFileRepository(ABC):
    """Карточки клиентов."""

    @abstractmethod
    def add(self, client_file: ClientFile) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, master_id: UUID, client_id: UUID) -> ClientFile | None:
        """Карточка клиента у мастера."""
