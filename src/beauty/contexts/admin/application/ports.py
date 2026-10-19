"""Порты Admin: изменения через контексты-владельцы и отчёты (только чтение).

Панель ничего не меняет в чужих таблицах сама: мастера — Tenancy, агент — Agent,
блокировка клиента — Identity. Отчёты — read-модель поверх схем всех контекстов в форме
контракта (``dict``), их меняет только отчётный адаптер.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import UUID

type Report = dict[str, Any]


@dataclass(frozen=True, slots=True)
class MasterDraft:
    """Новый мастер."""

    slug: str
    display_name: str
    name_nominative: str
    name_genitive: str
    name_dative: str
    specialty: str
    timezone: str
    owner_phone: str | None


class Platform(ABC):
    """Изменения в контекстах-владельцах."""

    @abstractmethod
    async def register_master(self, draft: MasterDraft) -> UUID:
        """Завести мастера (черновик) и, если задан, владельца."""

    @abstractmethod
    async def set_owner(self, master_id: UUID, phone: str) -> None:
        """Телефон владельца страницы."""

    @abstractmethod
    async def set_published(self, master_id: UUID, published: bool) -> None:
        """Опубликовать или скрыть страницу."""

    @abstractmethod
    async def set_agent(self, master_id: UUID, enabled: bool) -> None:
        """Включить или выключить ИИ-администратора (профиль должен быть подключён)."""

    @abstractmethod
    async def set_client_blocked(self, client_id: UUID, blocked: bool, reason: str | None) -> None:
        """Заблокировать или разблокировать клиента."""


class Reports(ABC):
    """Отчёты для панели (в форме контракта)."""

    @abstractmethod
    async def dashboard(self) -> Report:
        """Сводка."""

    @abstractmethod
    async def masters(self, query: str | None, status: str | None) -> list[Report]:
        """Мастера."""

    @abstractmethod
    async def master(self, master_id: UUID) -> Report | None:
        """Карточка мастера."""

    @abstractmethod
    async def clients(self, query: str | None, blocked: bool | None, limit: int, offset: int) -> Report:
        """Клиенты: ``{items, total}``."""

    @abstractmethod
    async def client(self, client_id: UUID) -> Report | None:
        """Клиент."""

    @abstractmethod
    async def agent(self) -> Report:
        """ИИ-администратор."""

    @abstractmethod
    async def system(self) -> Report:
        """Состояние системы."""
