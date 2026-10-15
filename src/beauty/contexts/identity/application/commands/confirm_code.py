"""Сценарий: пользователь выбрал код сверки в боте."""

from __future__ import annotations

from dataclasses import dataclass

from beauty.contexts.identity.application.dto import CodeConfirmationResult
from beauty.contexts.identity.application.errors import ChallengeNotFoundError
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.contexts.identity.domain.value_objects import AuthNonce, ConfirmationCode, TelegramUserId
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class ConfirmChallengeCode(Command[CodeConfirmationResult]):
    """Сверить выбранный код."""

    nonce: str
    telegram_user_id: int
    code: str


class ConfirmChallengeCodeHandler(Handler[ConfirmChallengeCode, CodeConfirmationResult]):
    """Сверяет код; неверный код отклоняет вход, и это сохраняется."""

    def __init__(self, uow: IdentityUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: ConfirmChallengeCode) -> CodeConfirmationResult:
        """Сверить код и сохранить исход."""
        now = self._clock.now()
        async with self._uow as uow:
            challenge = await uow.challenges.get_by_nonce(AuthNonce(message.nonce))
            if challenge is None:
                raise ChallengeNotFoundError()
            accepted = challenge.confirm_code(
                TelegramUserId(message.telegram_user_id), ConfirmationCode(message.code), now
            )
            await uow.commit()
        return CodeConfirmationResult(accepted=accepted)
