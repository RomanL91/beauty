"""Сценарий: выход (отзыв сессии)."""

from __future__ import annotations

from dataclasses import dataclass

from beauty.contexts.identity.application.errors import InvalidSessionError
from beauty.contexts.identity.application.services.refresh_token import RefreshToken
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class RevokeSession(Command[None]):
    """Отозвать сессию по refresh-токену."""

    refresh_token: str | None


class RevokeSessionHandler(Handler[RevokeSession, None]):
    """Отзывает сессию; выход идемпотентен и не сообщает, существовала ли сессия."""

    def __init__(self, uow: IdentityUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: RevokeSession) -> None:
        """Отозвать сессию, если токен её."""
        try:
            presented = RefreshToken.decode(message.refresh_token)
        except InvalidSessionError:
            return
        async with self._uow as uow:
            session = await uow.sessions.get(presented.session_id)
            if session is None or not session.refresh_secret.matches(presented.secret):
                return
            session.revoke(self._clock.now(), reason="logout")
            await uow.commit()
