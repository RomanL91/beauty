"""Аутентификация клиента по access-токену (``Authorization: Bearer``).

Проверку подписи и срока делает Identity; остальным контекстам нужен лишь id
учётной записи, поэтому зависимость FastAPI получает функцию «токен → account id» и не
знает о JWT.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import Request

from beauty.shared.application.errors import ApplicationError
from beauty.shared.domain.errors import DomainError


class UnauthenticatedError(ApplicationError):
    """Нужен вход: access-токен отсутствует, недействителен или истёк."""

    code = "invalid_session"


class BearerAuth:
    """Зависимость FastAPI: id учётной записи клиента или 401 (problem+json)."""

    def __init__(self, verify: Callable[[str], UUID]) -> None:
        """``verify`` бросает доменную или прикладную ошибку для плохого токена."""
        self._verify = verify

    async def __call__(self, request: Request) -> UUID:
        """Достать и проверить токен."""
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise UnauthenticatedError()
        try:
            return self._verify(token.strip())
        except (DomainError, ApplicationError) as error:
            raise UnauthenticatedError() from error
