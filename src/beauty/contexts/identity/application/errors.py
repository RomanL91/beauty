"""Прикладные ошибки Identity."""

from __future__ import annotations

from beauty.shared.application.errors import AccessDeniedError, ConflictError, NotFoundError


class ChallengeNotFoundError(NotFoundError):
    """Вход не найден — начните заново."""

    code = "challenge_not_found"


class NoChallengeAwaitingContactError(NotFoundError):
    """Нет активного входа, ожидающего контакт. Начните вход на странице мастера."""

    code = "no_challenge_awaiting_contact"


class InvalidSessionError(AccessDeniedError):
    """Сессия недействительна — войдите заново."""

    code = "invalid_session"


class SessionReuseError(AccessDeniedError):
    """Обнаружено повторное использование токена; сессия отозвана."""

    code = "session_reuse_detected"


class IdentityConflictError(ConflictError):
    """Номер уже принадлежит другой учётной записи — нужна помощь поддержки."""

    code = "identity_conflict"


class AccountBlockedError(AccessDeniedError):
    """Учётная запись заблокирована хозяином сервиса."""

    code = "account_blocked"


class AccountNotFoundError(NotFoundError):
    """Учётной записи нет."""

    code = "account_not_found"
