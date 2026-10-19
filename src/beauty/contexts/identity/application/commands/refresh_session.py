"""Сценарий: обновление access-токена с ротацией refresh-токена."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from beauty.contexts.identity.application.dto import SessionTokens
from beauty.contexts.identity.application.errors import (
    AccountBlockedError,
    InvalidSessionError,
    SessionReuseError,
)
from beauty.contexts.identity.application.ports import AccessTokenIssuer, SecretGenerator
from beauty.contexts.identity.application.services.refresh_token import RefreshToken
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.contexts.identity.domain.client_session import RotationOutcome
from beauty.contexts.identity.domain.errors import SessionInactive
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.secrets import HashedSecret


@dataclass(frozen=True, slots=True)
class RefreshSession(Command[SessionTokens]):
    """Обновить сессию по refresh-токену."""

    refresh_token: str | None


class RefreshSessionHandler(Handler[RefreshSession, SessionTokens]):
    """Ротирует refresh-токен; при повторном использовании отзывает сессию."""

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        clock: Clock,
        secrets: SecretGenerator,
        access_tokens: AccessTokenIssuer,
        refresh_ttl: timedelta,
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._secrets = secrets
        self._access_tokens = access_tokens
        self._refresh_ttl = refresh_ttl

    async def handle(self, message: RefreshSession) -> SessionTokens:
        """Ротировать токен и выпустить новый access."""
        presented = RefreshToken.decode(message.refresh_token)
        now = self._clock.now()
        new_secret = self._secrets.token(32)
        async with self._uow as uow:
            session = await uow.sessions.get(presented.session_id)
            if session is None:
                raise InvalidSessionError()
            account = await uow.accounts.get(session.account_id)
            if account is not None and account.blocked:
                session.revoke(now, "account_blocked")
                await uow.commit()
                raise AccountBlockedError()
            try:
                outcome = session.rotate(
                    presented.secret, HashedSecret.of(new_secret), now, self._refresh_ttl
                )
            except SessionInactive as error:
                raise InvalidSessionError() from error
            await uow.commit()
        if outcome is RotationOutcome.REUSE_DETECTED:
            raise SessionReuseError()
        access = self._access_tokens.issue(session.account_id, session.id, now)
        rotated = outcome is RotationOutcome.ROTATED
        return SessionTokens(
            account_id=session.account_id,
            access_token=access.value,
            access_expires_at=access.expires_at,
            refresh_token=RefreshToken(session.id, new_secret).encode() if rotated else None,
            refresh_expires_at=session.expires_at,
        )
