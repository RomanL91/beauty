"""Доменные события контекста Identity.

Поля событий — примитивы: событие — контракт с другими контекстами (CRM
привязывает карточки клиентов по ``ClientAuthenticated``), и он не должен зависеть
от внутренних value objects Identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.shared.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class AuthChallengeCompleted(DomainEvent):
    """Клиент подтвердил вход в Telegram; браузер может забрать сессию."""

    routing_key = "identity.auth_challenge.completed"

    challenge_id: UUID


@dataclass(frozen=True, kw_only=True)
class AuthChallengeRejected(DomainEvent):
    """Вход отклонён (например, выбран неверный код сверки)."""

    routing_key = "identity.auth_challenge.rejected"

    challenge_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class ClientRegistered(DomainEvent):
    """Создана новая учётная запись клиента."""

    routing_key = "identity.client.registered"

    account_id: UUID
    phone: str


@dataclass(frozen=True, kw_only=True)
class ClientAuthenticated(DomainEvent):
    """Клиент вошёл; телефон верифицирован Telegram в этот момент."""

    routing_key = "identity.client.authenticated"

    account_id: UUID
    phone: str
    telegram_user_id: int


@dataclass(frozen=True, kw_only=True)
class ClientPhoneChanged(DomainEvent):
    """У клиента сменился номер телефона в Telegram."""

    routing_key = "identity.client.phone_changed"

    account_id: UUID
    old_phone: str
    new_phone: str


@dataclass(frozen=True, kw_only=True)
class ClientTelegramRelinked(DomainEvent):
    """Номер клиента теперь привязан к другому аккаунту Telegram."""

    routing_key = "identity.client.telegram_relinked"

    account_id: UUID
    telegram_user_id: int


@dataclass(frozen=True, kw_only=True)
class ClientSessionRevoked(DomainEvent):
    """Сессия клиента отозвана."""

    routing_key = "identity.session.revoked"

    session_id: UUID
    account_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class ClientBlocked(DomainEvent):
    """Хозяин сервиса заблокировал (``blocked=False`` — разблокировал) клиента."""

    routing_key = "identity.client.blocked"

    account_id: UUID
    blocked: bool
