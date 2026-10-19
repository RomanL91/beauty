"""Агрегат ``ClientAccount`` — глобальная учётная запись клиента платформы.

Учётная запись одна на все страницы мастеров. Её ключи — верифицированный
Telegram номер телефона и id пользователя Telegram; оба уникальны.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from beauty.contexts.identity.domain.events import (
    ClientAuthenticated,
    ClientBlocked,
    ClientPhoneChanged,
    ClientRegistered,
    ClientTelegramRelinked,
)
from beauty.contexts.identity.domain.value_objects import PhoneNumber, TelegramUserId
from beauty.shared.domain.aggregate import AggregateRoot


class ClientAccount(AggregateRoot):
    """Учётная запись клиента."""

    def __init__(
        self, account_id: UUID, phone: PhoneNumber, telegram_user_id: TelegramUserId, created_at: datetime
    ) -> None:
        """Создать учётную запись (используйте ``register``)."""
        self.id = account_id
        self.phone = phone
        self.telegram_user_id = telegram_user_id
        self.created_at = created_at
        self.updated_at = created_at
        self.last_authenticated_at: datetime | None = None
        self.blocked_at: datetime | None = None
        self.blocked_reason: str | None = None

    @classmethod
    def register(
        cls, *, account_id: UUID, phone: PhoneNumber, telegram_user_id: TelegramUserId, now: datetime
    ) -> ClientAccount:
        """Зарегистрировать нового клиента."""
        account = cls(account_id, phone, telegram_user_id, now)
        account._record(ClientRegistered(occurred_at=now, account_id=account_id, phone=phone.value))
        return account

    def change_phone(self, phone: PhoneNumber, now: datetime) -> None:
        """Обновить номер (клиент сменил номер в Telegram)."""
        if phone == self.phone:
            return
        old = self.phone
        self.phone = phone
        self.updated_at = now
        self._record(
            ClientPhoneChanged(
                occurred_at=now, account_id=self.id, old_phone=old.value, new_phone=phone.value
            )
        )

    def relink_telegram(self, telegram_user_id: TelegramUserId, now: datetime) -> None:
        """Привязать номер к другому аккаунту Telegram (новый аккаунт на тот же номер)."""
        if telegram_user_id == self.telegram_user_id:
            return
        self.telegram_user_id = telegram_user_id
        self.updated_at = now
        self._record(
            ClientTelegramRelinked(
                occurred_at=now, account_id=self.id, telegram_user_id=telegram_user_id.value
            )
        )

    def authenticate(self, now: datetime) -> None:
        """Зафиксировать успешный вход."""
        self.last_authenticated_at = now
        self._record(
            ClientAuthenticated(
                occurred_at=now,
                account_id=self.id,
                phone=self.phone.value,
                telegram_user_id=self.telegram_user_id.value,
            )
        )

    @property
    def blocked(self) -> bool:
        """Заблокирован хозяином сервиса."""
        return self.blocked_at is not None

    def block(self, reason: str | None, now: datetime) -> bool:
        """Заблокировать (повтор — no-op, ``False``): вход и обновление сессии запрещены."""
        if self.blocked_at is not None:
            return False
        self.blocked_at = now
        self.blocked_reason = (reason or "").strip()[:300] or None
        self.updated_at = now
        self._record(ClientBlocked(occurred_at=now, account_id=self.id, blocked=True))
        return True

    def unblock(self, now: datetime) -> bool:
        """Снять блокировку (не заблокирован — no-op, ``False``)."""
        if self.blocked_at is None:
            return False
        self.blocked_at = None
        self.blocked_reason = None
        self.updated_at = now
        self._record(ClientBlocked(occurred_at=now, account_id=self.id, blocked=False))
        return True
