"""Порты репозиториев контекста Identity."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from beauty.contexts.identity.domain.auth_challenge import AuthChallenge
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.client_session import ClientSession
from beauty.contexts.identity.domain.value_objects import AuthNonce, PhoneNumber, TelegramUserId


class AuthChallengeRepository(ABC):
    """Коллекция попыток входа."""

    @abstractmethod
    def add(self, challenge: AuthChallenge) -> None:
        """Добавить новую попытку."""

    @abstractmethod
    async def get(self, challenge_id: UUID) -> AuthChallenge | None:
        """Найти по id."""

    @abstractmethod
    async def get_by_nonce(self, nonce: AuthNonce) -> AuthChallenge | None:
        """Найти по токену из deep link."""

    @abstractmethod
    async def get_awaiting_contact(
        self, telegram_user: TelegramUserId, now: datetime
    ) -> AuthChallenge | None:
        """Последняя неистёкшая попытка пользователя, ожидающая контакт."""


class ClientAccountRepository(ABC):
    """Коллекция учётных записей клиентов."""

    @abstractmethod
    def add(self, account: ClientAccount) -> None:
        """Добавить новую учётную запись."""

    @abstractmethod
    async def get(self, account_id: UUID) -> ClientAccount | None:
        """Найти по id."""

    @abstractmethod
    async def get_by_telegram_user(self, telegram_user: TelegramUserId) -> ClientAccount | None:
        """Найти по id пользователя Telegram."""

    @abstractmethod
    async def get_by_phone(self, phone: PhoneNumber) -> ClientAccount | None:
        """Найти по номеру телефона."""


class ClientSessionRepository(ABC):
    """Коллекция сессий."""

    @abstractmethod
    def add(self, session: ClientSession) -> None:
        """Добавить новую сессию."""

    @abstractmethod
    async def get(self, session_id: UUID) -> ClientSession | None:
        """Найти по id."""
