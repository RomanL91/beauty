"""Агрегат ``Administrator`` — учётная запись хозяина сервиса (или его помощника).

Вход — логин и пароль. Перебор: после ``MAX_FAILURES`` неверных паролей подряд вход
закрыт на ``LOCK_FOR``; успешный вход сбрасывает счётчик.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from uuid import UUID

from beauty.contexts.admin.domain.errors import InvalidAdminLogin, InvalidAdminName
from beauty.shared.domain.aggregate import AggregateRoot

MAX_FAILURES = 5
LOCK_FOR = timedelta(minutes=15)
_LOGIN = re.compile(r"^[a-z0-9._-]{3,64}$")


def normalize_login(login: str) -> str:
    """Логин без регистра и пробелов по краям."""
    return login.strip().lower()


class Administrator(AggregateRoot):
    """Администратор панели."""

    def __init__(
        self, admin_id: UUID, login: str, display_name: str, password_hash: str, created_at: datetime
    ) -> None:
        """Создать (используйте ``register``)."""
        self.id = admin_id
        self.login = login
        self.display_name = display_name
        self.password_hash = password_hash
        self.active = True
        self.failed_attempts = 0
        self.locked_until: datetime | None = None
        self.last_login_at: datetime | None = None
        self.password_changed_at = created_at
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def register(
        cls, *, admin_id: UUID, login: str, display_name: str, password_hash: str, now: datetime
    ) -> Administrator:
        """Новый администратор (пароль уже захеширован)."""
        normalized = normalize_login(login)
        if not _LOGIN.match(normalized):
            raise InvalidAdminLogin("Логин — 3–64 символа: латиница, цифры, точка, дефис, подчёркивание")
        return cls(admin_id, normalized, _name(display_name), password_hash, now)

    def locked(self, now: datetime) -> bool:
        """Вход временно закрыт после перебора."""
        return self.locked_until is not None and now < self.locked_until

    def login_failed(self, now: datetime) -> None:
        """Неверный пароль: счётчик; на ``MAX_FAILURES`` — блокировка на ``LOCK_FOR``."""
        self.failed_attempts += 1
        if self.failed_attempts >= MAX_FAILURES:
            self.locked_until = now + LOCK_FOR
            self.failed_attempts = 0
        self.updated_at = now

    def logged_in(self, now: datetime) -> None:
        """Успешный вход."""
        self.failed_attempts = 0
        self.locked_until = None
        self.last_login_at = now
        self.updated_at = now

    def change_password(self, password_hash: str, now: datetime) -> None:
        """Новый пароль (сессии отзывает прикладной слой)."""
        self.password_hash = password_hash
        self.password_changed_at = now
        self.failed_attempts = 0
        self.locked_until = None
        self.updated_at = now

    def set_active(self, active: bool, now: datetime) -> bool:
        """Включить или отключить; ``False`` — уже так."""
        if self.active is active:
            return False
        self.active = active
        self.updated_at = now
        return True


def _name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > 80:
        raise InvalidAdminName("Имя — от 1 до 80 символов")
    return cleaned
