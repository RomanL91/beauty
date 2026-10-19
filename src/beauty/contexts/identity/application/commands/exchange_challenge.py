"""Сценарий: браузер обменивает завершённый вход на сессию."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from beauty.contexts.identity.application.dto import SessionTokens
from beauty.contexts.identity.application.errors import AccountBlockedError, ChallengeNotFoundError
from beauty.contexts.identity.application.ports import AccessTokenIssuer, SecretGenerator
from beauty.contexts.identity.application.services.refresh_token import RefreshToken
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.contexts.identity.domain.client_session import ClientSession
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.domain.secrets import HashedSecret


@dataclass(frozen=True, slots=True)
class ExchangeChallengeForSession(Command[SessionTokens]):
    """Обменять вход на сессию (секрет — из httpOnly-cookie браузера)."""

    challenge_id: UUID
    browser_secret: str


class ExchangeChallengeForSessionHandler(Handler[ExchangeChallengeForSession, SessionTokens]):
    """Одноразово гасит challenge и открывает сессию."""

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        clock: Clock,
        id_generator: IdGenerator,
        secrets: SecretGenerator,
        access_tokens: AccessTokenIssuer,
        refresh_ttl: timedelta,
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._id_generator = id_generator
        self._secrets = secrets
        self._access_tokens = access_tokens
        self._refresh_ttl = refresh_ttl

    async def handle(self, message: ExchangeChallengeForSession) -> SessionTokens:
        """Погасить challenge, открыть сессию, выпустить токены."""
        now = self._clock.now()
        refresh_secret = self._secrets.token(32)
        async with self._uow as uow:
            challenge = await uow.challenges.get(message.challenge_id)
            if challenge is None:
                raise ChallengeNotFoundError()
            account_id = challenge.consume(message.browser_secret, now)
            account = await uow.accounts.get(account_id)
            if account is not None and account.blocked:
                await uow.commit()  # вход погашен: повторить его нельзя
                raise AccountBlockedError()
            session = ClientSession.open(
                session_id=self._id_generator.new(),
                account_id=account_id,
                refresh_secret=HashedSecret.of(refresh_secret),
                now=now,
                ttl=self._refresh_ttl,
            )
            uow.sessions.add(session)
            await uow.commit()
        access = self._access_tokens.issue(account_id, session.id, now)
        return SessionTokens(
            account_id=account_id,
            access_token=access.value,
            access_expires_at=access.expires_at,
            refresh_token=RefreshToken(session.id, refresh_secret).encode(),
            refresh_expires_at=session.expires_at,
        )
