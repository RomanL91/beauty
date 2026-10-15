"""Порты прикладного слоя Identity (реализуются в инфраструктуре)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.contexts.identity.domain.value_objects import AuthNonce


class SecretGenerator(ABC):
    """Генератор криптостойких случайных строк."""

    @abstractmethod
    def token(self, nbytes: int = 32) -> str:
        """URL-safe строка из ``nbytes`` случайных байт."""


@dataclass(frozen=True, slots=True)
class AccessToken:
    """Выпущенный access-токен."""

    value: str
    expires_at: datetime


class AccessTokenIssuer(ABC):
    """Выпуск access-токенов."""

    @abstractmethod
    def issue(self, account_id: UUID, session_id: UUID, now: datetime) -> AccessToken:
        """Выпустить токен для учётной записи и сессии."""


class DeepLinkBuilder(ABC):
    """Построитель ссылки на бота."""

    @abstractmethod
    def build(self, nonce: AuthNonce) -> str:
        """Ссылка ``t.me/<bot>?start=<nonce>``."""


@dataclass(frozen=True, slots=True)
class ChallengeStatusRecord:
    """Сырые данные о статусе входа для read-модели."""

    challenge_id: UUID
    status: str
    expires_at: datetime
    browser_secret_digest: str


class ChallengeStatusReader(ABC):
    """Read-модель статуса входа (CQRS: читаем напрямую, без агрегата)."""

    @abstractmethod
    async def read(self, challenge_id: UUID) -> ChallengeStatusRecord | None:
        """Прочитать статус входа."""
