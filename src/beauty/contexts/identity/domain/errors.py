"""Доменные ошибки контекста Identity."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError


class InvalidPhoneNumber(DomainError):
    """Номер телефона не похож на номер в формате E.164."""

    code = "invalid_phone"


class InvalidTelegramUserId(DomainError):
    """Некорректный идентификатор пользователя Telegram."""

    code = "invalid_telegram_user"


class InvalidConfirmationCode(DomainError):
    """Код сверки должен состоять из двух цифр."""

    code = "invalid_confirmation_code"


class InvalidAuthNonce(DomainError):
    """Некорректный одноразовый токен входа."""

    code = "invalid_nonce"


class ChallengeExpired(DomainError):
    """Время на вход истекло — начните вход заново."""

    code = "challenge_expired"


class ChallengeAlreadyClaimed(DomainError):
    """Этот вход уже подтверждается другим пользователем Telegram."""

    code = "challenge_already_claimed"


class ChallengeForeignUser(DomainError):
    """Вход начат другим пользователем Telegram."""

    code = "challenge_foreign_user"


class InvalidChallengeState(DomainError):
    """Операция недоступна на текущем шаге входа."""

    code = "invalid_challenge_state"


class BrowserSecretMismatch(DomainError):
    """Вход был начат в другом браузере."""

    code = "browser_secret_mismatch"


class ContactNotOwnedBySender(DomainError):
    """Можно поделиться только своим контактом."""

    code = "contact_not_owned"


class SessionInactive(DomainError):
    """Сессия истекла или отозвана — войдите заново."""

    code = "session_inactive"
