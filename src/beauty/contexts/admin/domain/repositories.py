"""Порты репозиториев Admin."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from beauty.contexts.admin.domain.admin import Administrator
from beauty.contexts.admin.domain.audit import AuditEntry
from beauty.contexts.admin.domain.session import AdminSession


class AdministratorRepository(ABC):
    """Администраторы."""

    @abstractmethod
    def add(self, admin: Administrator) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, admin_id: UUID) -> Administrator | None:
        """По id."""

    @abstractmethod
    async def by_login(self, login: str) -> Administrator | None:
        """По логину (уже нормализованному)."""

    @abstractmethod
    async def all(self) -> list[Administrator]:
        """Все, по логину."""


class AdminSessionRepository(ABC):
    """Сессии."""

    @abstractmethod
    def add(self, session: AdminSession) -> None:
        """Добавить."""

    @abstractmethod
    async def get(self, session_id: UUID) -> AdminSession | None:
        """По id."""

    @abstractmethod
    async def active_of(self, admin_id: UUID) -> list[AdminSession]:
        """Неотозванные сессии администратора."""


class AuditRepository(ABC):
    """Журнал действий."""

    @abstractmethod
    def add(self, entry: AuditEntry) -> None:
        """Записать."""

    @abstractmethod
    async def page(self, before: UUID | None, limit: int) -> list[AuditEntry]:
        """Новые сверху; ``before`` — курсор (id старше которого)."""
