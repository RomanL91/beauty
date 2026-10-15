"""Агрегат ``ClientSession`` — серверная сессия с ротируемым refresh-токеном.

Короткоживущий access-токен (JWT) проверяется без БД, а refresh-токен хранится
только в виде хеша и меняется при каждом обновлении. Если предъявлен уже
заменённый refresh-токен, значит его скопировали: сессия отзывается целиком
(refresh token reuse detection), и вход требуется заново и владельцу, и вору.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from beauty.contexts.identity.domain.errors import SessionInactive
from beauty.contexts.identity.domain.events import ClientSessionRevoked
from beauty.shared.domain.aggregate import AggregateRoot
from beauty.shared.domain.secrets import HashedSecret


class RotationOutcome(StrEnum):
    """Результат ротации refresh-токена.

    ``CONCURRENT`` — предъявлен только что заменённый токен в пределах окна
    снисхождения: две вкладки PWA обновили сессию одновременно (cookie общий).
    Это не кража: новый access выдаётся, а refresh-cookie уже обновлён первым
    ответом.
    """

    ROTATED = "rotated"
    CONCURRENT = "concurrent"
    REUSE_DETECTED = "reuse_detected"


class ClientSession(AggregateRoot):
    """Сессия клиента на одном устройстве."""

    def __init__(
        self,
        session_id: UUID,
        account_id: UUID,
        refresh_secret: HashedSecret,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        """Создать сессию (используйте ``open``)."""
        self.id = session_id
        self.account_id = account_id
        self.refresh_secret = refresh_secret
        self.created_at = created_at
        self.expires_at = expires_at
        self.previous_refresh_secret: HashedSecret | None = None
        self.rotated_at: datetime | None = None
        self.revoked_at: datetime | None = None
        self.revoke_reason: str | None = None

    @classmethod
    def open(
        cls,
        *,
        session_id: UUID,
        account_id: UUID,
        refresh_secret: HashedSecret,
        now: datetime,
        ttl: timedelta,
    ) -> ClientSession:
        """Открыть сессию."""
        return cls(session_id, account_id, refresh_secret, now, now + ttl)

    def is_active(self, now: datetime) -> bool:
        """Сессия не отозвана и не истекла."""
        return self.revoked_at is None and now < self.expires_at

    def rotate(
        self,
        presented_secret: str,
        new_secret: HashedSecret,
        now: datetime,
        ttl: timedelta,
        grace: timedelta = timedelta(seconds=30),
    ) -> RotationOutcome:
        """Заменить refresh-токен; при повторном использовании старого — отозвать сессию.

        Скользящий срок жизни: каждое обновление продлевает сессию на ``ttl``.
        """
        if not self.is_active(now):
            raise SessionInactive()
        if self.refresh_secret.matches(presented_secret):
            self.previous_refresh_secret = self.refresh_secret
            self.refresh_secret = new_secret
            self.rotated_at = now
            self.expires_at = now + ttl
            return RotationOutcome.ROTATED
        if self._within_grace(presented_secret, now, grace):
            return RotationOutcome.CONCURRENT
        self.revoke(now, reason="refresh_reuse_detected")
        return RotationOutcome.REUSE_DETECTED

    def _within_grace(self, presented_secret: str, now: datetime, grace: timedelta) -> bool:
        """Предъявлен предыдущий токен сразу после ротации."""
        return (
            self.previous_refresh_secret is not None
            and self.rotated_at is not None
            and now - self.rotated_at <= grace
            and self.previous_refresh_secret.matches(presented_secret)
        )

    def revoke(self, now: datetime, reason: str) -> None:
        """Отозвать сессию (повторный отзыв — no-op)."""
        if self.revoked_at is not None:
            return
        self.revoked_at = now
        self.revoke_reason = reason
        self._record(
            ClientSessionRevoked(
                occurred_at=now, session_id=self.id, account_id=self.account_id, reason=reason
            )
        )
