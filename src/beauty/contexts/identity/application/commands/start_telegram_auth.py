"""Сценарий: браузер начинает вход через Telegram."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from beauty.contexts.identity.application.dto import StartedChallenge
from beauty.contexts.identity.application.ports import DeepLinkBuilder, SecretGenerator
from beauty.contexts.identity.application.services.confirmation import ChallengeConfirmationPolicy
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.contexts.identity.domain.auth_challenge import AuthChallenge
from beauty.contexts.identity.domain.value_objects import AuthNonce
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.domain.secrets import HashedSecret


@dataclass(frozen=True, slots=True)
class StartTelegramAuth(Command[StartedChallenge]):
    """Начать вход."""


class StartTelegramAuthHandler(Handler[StartTelegramAuth, StartedChallenge]):
    """Создаёт challenge: nonce для deep link, секрет браузера и код сверки.

    Nonce (24 байта) попадает в Telegram и логи бота, поэтому сам по себе ничего не
    даёт: забрать сессию может только браузер с секретом (32 байта) из
    httpOnly-cookie, а в БД хранится лишь хеш секрета.
    """

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        clock: Clock,
        id_generator: IdGenerator,
        secrets: SecretGenerator,
        policy: ChallengeConfirmationPolicy,
        deep_links: DeepLinkBuilder,
        ttl: timedelta,
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._id_generator = id_generator
        self._secrets = secrets
        self._policy = policy
        self._deep_links = deep_links
        self._ttl = ttl

    async def handle(self, message: StartTelegramAuth) -> StartedChallenge:
        """Создать и сохранить challenge."""
        now = self._clock.now()
        nonce = AuthNonce(self._secrets.token(24))
        browser_secret = self._secrets.token(32)
        challenge = AuthChallenge.start(
            challenge_id=self._id_generator.new(),
            nonce=nonce,
            browser_secret=HashedSecret.of(browser_secret),
            confirmation_code=self._policy.generate_code(),
            now=now,
            ttl=self._ttl,
        )
        async with self._uow as uow:
            uow.challenges.add(challenge)
            await uow.commit()
        return StartedChallenge(
            challenge_id=challenge.id,
            deep_link=self._deep_links.build(nonce),
            confirmation_code=challenge.confirmation_code.value,
            expires_at=challenge.expires_at,
            browser_secret=browser_secret,
        )
