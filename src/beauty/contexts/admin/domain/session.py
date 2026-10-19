"""Агрегат ``AdminSession`` — вход администратора (cookie ``bk_admin``).

В cookie — ``<id сессии>.<секрет>``; в базе — только SHA-256 секрета. CSRF-токен
сессии браузер получает в ответе входа и шлёт заголовком в изменяющих запросах.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from beauty.shared.domain.aggregate import AggregateRoot
from beauty.shared.domain.secrets import HashedSecret


class AdminSession(AggregateRoot):
    """Сессия администратора."""

    def __init__(
        self,
        session_id: UUID,
        admin_id: UUID,
        secret: HashedSecret,
        csrf_token: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        """Создать (используйте ``open``)."""
        self.id = session_id
        self.admin_id = admin_id
        self.secret = secret
        self.csrf_token = csrf_token
        self.created_at = created_at
        self.expires_at = expires_at
        self.revoked_at: datetime | None = None

    @classmethod
    def open(
        cls,
        *,
        session_id: UUID,
        admin_id: UUID,
        secret: str,
        csrf_token: str,
        now: datetime,
        ttl: timedelta,
    ) -> AdminSession:
        """Открыть сессию."""
        return cls(session_id, admin_id, HashedSecret.of(secret), csrf_token, now, now + ttl)

    def valid(self, secret: str, now: datetime) -> bool:
        """Секрет совпал, сессия не отозвана и не истекла."""
        return self.revoked_at is None and now < self.expires_at and self.secret.matches(secret)

    def revoke(self, now: datetime) -> None:
        """Отозвать (повтор — no-op)."""
        if self.revoked_at is None:
            self.revoked_at = now
