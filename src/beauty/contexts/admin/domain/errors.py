"""Доменные ошибки контекста Admin."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError


class WeakPassword(DomainError):
    """Пароль короче минимума или слишком длинный."""

    code = "weak_password"


class InvalidAdminLogin(DomainError):
    """Логин: латиница, цифры, точка, дефис, подчёркивание; 3–64 символа."""

    code = "invalid_admin_login"


class InvalidAdminName(DomainError):
    """Имя администратора пустое или длиннее 80 символов."""

    code = "invalid_admin_name"
