"""Поиск или создание учётной записи по верифицированному контакту (Chain of Responsibility).

Звенья проверяются по порядку:

1. ``ByTelegramUser`` — клиент уже входил с этого аккаунта Telegram. Если номер
   изменился — обновляем номер (если он не занят другой учётной записью);
2. ``ByPhone`` — номер известен, но аккаунт Telegram новый (переустановка, новый
   аккаунт на тот же номер) — перепривязываем Telegram;
3. ``Register`` — новый клиент.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from beauty.contexts.identity.application.errors import IdentityConflictError
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.repositories import ClientAccountRepository
from beauty.contexts.identity.domain.value_objects import PhoneNumber, TelegramUserId
from beauty.shared.domain.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class ResolutionRequest:
    """Данные для поиска учётной записи."""

    phone: PhoneNumber
    telegram_user: TelegramUserId
    now: datetime


@dataclass(frozen=True, slots=True)
class ResolvedAccount:
    """Найденная или созданная учётная запись."""

    account: ClientAccount
    is_new: bool


class AccountResolutionStep(ABC):
    """Звено цепочки."""

    def __init__(
        self, accounts: ClientAccountRepository, successor: AccountResolutionStep | None = None
    ) -> None:
        """Связать звено с репозиторием и следующим звеном."""
        self._accounts = accounts
        self._successor = successor

    async def resolve(self, request: ResolutionRequest) -> ResolvedAccount:
        """Попробовать разрешить запрос или передать дальше."""
        resolved = await self._try_resolve(request)
        if resolved is not None:
            return resolved
        if self._successor is None:  # pragma: no cover - цепочка всегда заканчивается Register
            raise LookupError("Цепочка поиска учётной записи не завершилась")
        return await self._successor.resolve(request)

    @abstractmethod
    async def _try_resolve(self, request: ResolutionRequest) -> ResolvedAccount | None:
        """Вернуть результат или ``None``, если звено не применимо."""


class ByTelegramUser(AccountResolutionStep):
    """Учётная запись с тем же аккаунтом Telegram."""

    async def _try_resolve(self, request: ResolutionRequest) -> ResolvedAccount | None:
        """Найти по Telegram id и при необходимости обновить номер."""
        account = await self._accounts.get_by_telegram_user(request.telegram_user)
        if account is None:
            return None
        if account.phone != request.phone:
            owner = await self._accounts.get_by_phone(request.phone)
            if owner is not None and owner.id != account.id:
                raise IdentityConflictError()
            account.change_phone(request.phone, request.now)
        return ResolvedAccount(account, is_new=False)


class ByPhone(AccountResolutionStep):
    """Учётная запись с тем же номером, но другим аккаунтом Telegram."""

    async def _try_resolve(self, request: ResolutionRequest) -> ResolvedAccount | None:
        """Найти по номеру и перепривязать Telegram."""
        account = await self._accounts.get_by_phone(request.phone)
        if account is None:
            return None
        account.relink_telegram(request.telegram_user, request.now)
        return ResolvedAccount(account, is_new=False)


class Register(AccountResolutionStep):
    """Новый клиент."""

    def __init__(self, accounts: ClientAccountRepository, id_generator: IdGenerator) -> None:
        """Последнее звено цепочки."""
        super().__init__(accounts)
        self._id_generator = id_generator

    async def _try_resolve(self, request: ResolutionRequest) -> ResolvedAccount | None:
        """Зарегистрировать учётную запись."""
        account = ClientAccount.register(
            account_id=self._id_generator.new(),
            phone=request.phone,
            telegram_user_id=request.telegram_user,
            now=request.now,
        )
        self._accounts.add(account)
        return ResolvedAccount(account, is_new=True)


class AccountResolver:
    """Собирает цепочку поверх репозитория текущего Unit of Work."""

    def __init__(self, id_generator: IdGenerator) -> None:
        """Запомнить генератор id для регистрации."""
        self._id_generator = id_generator

    async def resolve(self, accounts: ClientAccountRepository, request: ResolutionRequest) -> ResolvedAccount:
        """Найти или создать учётную запись."""
        chain = ByTelegramUser(accounts, ByPhone(accounts, Register(accounts, self._id_generator)))
        return await chain.resolve(request)
