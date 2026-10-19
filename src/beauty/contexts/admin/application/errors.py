"""Прикладные ошибки Admin."""

from __future__ import annotations

from beauty.shared.application.errors import AccessDeniedError, ConflictError, NotFoundError


class InvalidCredentialsError(AccessDeniedError):
    """Неверный логин или пароль (одинаково для обоих)."""

    code = "invalid_credentials"


class AdminLockedError(AccessDeniedError):
    """Слишком много неверных паролей — вход закрыт на время."""

    code = "admin_locked"


class AdminUnauthorizedError(AccessDeniedError):
    """Нет действующей сессии администратора."""

    code = "admin_unauthorized"


class CsrfFailedError(AccessDeniedError):
    """Нет или неверный заголовок ``X-CSRF-Token``."""

    code = "csrf_failed"


class WrongPasswordError(AccessDeniedError):
    """Текущий пароль указан неверно."""

    code = "wrong_password"


class AdminLoginTakenError(ConflictError):
    """Логин занят."""

    code = "admin_login_taken"


class CannotDisableSelfError(ConflictError):
    """Себя отключить нельзя."""

    code = "cannot_disable_self"


class AdminNotFoundError(NotFoundError):
    """Администратора нет."""

    code = "admin_not_found"
