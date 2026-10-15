"""Формат refresh-токена ``<session_id>.<secret>``."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.identity.application.errors import InvalidSessionError


@dataclass(frozen=True, slots=True)
class RefreshToken:
    """Разобранный refresh-токен."""

    session_id: UUID
    secret: str

    def encode(self) -> str:
        """Строковое представление для cookie."""
        return f"{self.session_id}.{self.secret}"

    @classmethod
    def decode(cls, raw: str | None) -> RefreshToken:
        """Разобрать строку; любой мусор — недействительная сессия."""
        if not raw or "." not in raw:
            raise InvalidSessionError()
        session_part, secret = raw.split(".", 1)
        try:
            session_id = UUID(session_part)
        except ValueError as error:
            raise InvalidSessionError() from error
        if not secret:
            raise InvalidSessionError()
        return cls(session_id, secret)
