"""DTO — результаты сценариев Identity для слоя представления."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StartedChallenge:
    """Начатый вход.

    ``browser_secret`` — сырой секрет; API кладёт его в httpOnly-cookie и больше
    нигде не показывает.
    """

    challenge_id: UUID
    deep_link: str
    confirmation_code: str
    expires_at: datetime
    browser_secret: str


class ClaimStep(StrEnum):
    """Следующий шаг пользователя в боте."""

    ASK_CODE = "ask_code"
    ASK_CONTACT = "ask_contact"


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """Результат открытия deep link в боте."""

    challenge_id: UUID
    step: ClaimStep
    code_options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CodeConfirmationResult:
    """Результат сверки кода."""

    accepted: bool


@dataclass(frozen=True, slots=True)
class ContactAccepted:
    """Контакт принят, вход завершён."""

    masked_phone: str
    is_new_client: bool


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """Токены сессии.

    ``refresh_token`` имеет вид ``<session_id>.<secret>``: id нужен, чтобы найти
    сессию по первичному ключу, а сравнение секрета идёт по хешу. ``None`` — токен
    не менялся (параллельное обновление из второй вкладки), cookie трогать не нужно.
    """

    account_id: UUID
    access_token: str
    access_expires_at: datetime
    refresh_token: str | None
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class ChallengeStatusView:
    """Статус входа для браузера."""

    challenge_id: UUID
    status: str
    expires_at: datetime
