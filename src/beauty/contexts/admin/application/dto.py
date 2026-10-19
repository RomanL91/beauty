"""DTO Admin."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.admin.domain.admin import Administrator
from beauty.contexts.admin.domain.audit import AuditEntry


@dataclass(frozen=True, slots=True)
class AdminView:
    """Администратор (без пароля)."""

    id: UUID
    login: str
    display_name: str
    active: bool
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def of(cls, admin: Administrator) -> AdminView:
        """Из агрегата."""
        return cls(
            admin.id, admin.login, admin.display_name, admin.active, admin.created_at, admin.last_login_at
        )

    def json(self) -> dict[str, Any]:
        """В форме контракта ``AdminAccount``."""
        return {
            "id": str(self.id),
            "login": self.login,
            "display_name": self.display_name,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
            "last_login_at": None if self.last_login_at is None else self.last_login_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class AdminActor:
    """Кто действует: администратор текущей сессии."""

    admin_id: UUID
    login: str
    session_id: UUID


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    """Действующая сессия: администратор, CSRF-токен, срок."""

    admin: AdminView
    session_id: UUID
    csrf_token: str
    expires_at: datetime

    @property
    def actor(self) -> AdminActor:
        """Кто действует."""
        return AdminActor(self.admin.id, self.admin.login, self.session_id)

    def json(self) -> dict[str, Any]:
        """В форме контракта ``AdminSession``."""
        return {
            "admin": self.admin.json(),
            "csrf_token": self.csrf_token,
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Вход: сессия и значение cookie."""

    principal: AdminPrincipal
    cookie: str


def audit_json(entry: AuditEntry) -> dict[str, Any]:
    """Запись журнала в форме контракта ``AdminAuditEntry``."""
    return {
        "id": str(entry.id),
        "at": entry.created_at.isoformat(),
        "admin": entry.admin_login,
        "action": entry.action,
        "target": entry.target,
        "summary": entry.summary,
    }
