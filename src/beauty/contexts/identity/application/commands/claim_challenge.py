"""Сценарий: пользователь открыл deep link в боте."""

from __future__ import annotations

from dataclasses import dataclass

from beauty.contexts.identity.application.dto import ClaimResult
from beauty.contexts.identity.application.errors import ChallengeNotFoundError
from beauty.contexts.identity.application.services.confirmation import ChallengeConfirmationPolicy
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.contexts.identity.domain.value_objects import AuthNonce, TelegramUserId
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class ClaimChallenge(Command[ClaimResult]):
    """Закрепить вход за пользователем Telegram."""

    nonce: str
    telegram_user_id: int


class ClaimChallengeHandler(Handler[ClaimChallenge, ClaimResult]):
    """Закрепляет challenge и определяет следующий шаг по политике подтверждения."""

    def __init__(self, uow: IdentityUnitOfWork, clock: Clock, policy: ChallengeConfirmationPolicy) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._policy = policy

    async def handle(self, message: ClaimChallenge) -> ClaimResult:
        """Найти вход по nonce и закрепить его."""
        now = self._clock.now()
        telegram_user = TelegramUserId(message.telegram_user_id)
        async with self._uow as uow:
            challenge = await uow.challenges.get_by_nonce(AuthNonce(message.nonce))
            if challenge is None:
                raise ChallengeNotFoundError()
            challenge.claim(telegram_user, now)
            result = self._policy.after_claim(challenge, telegram_user, now)
            await uow.commit()
        return result
