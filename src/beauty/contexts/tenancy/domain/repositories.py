"""Порты репозиториев контекста Tenancy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from beauty.contexts.tenancy.domain.master import Master
from beauty.contexts.tenancy.domain.value_objects import MasterSlug


class MasterRepository(ABC):
    """Коллекция мастеров."""

    @abstractmethod
    def add(self, master: Master) -> None:
        """Добавить нового мастера."""

    @abstractmethod
    async def get(self, master_id: UUID) -> Master | None:
        """Найти по id."""

    @abstractmethod
    async def get_by_owner(self, phone: str) -> Master | None:
        """Мастер, привязанный к телефону владельца."""

    @abstractmethod
    async def get_by_slug(self, slug: MasterSlug) -> Master | None:
        """Найти по адресу страницы."""
