"""Запрос статуса входа браузером."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.identity.application.dto import ChallengeStatusView
from beauty.contexts.identity.application.errors import ChallengeNotFoundError
from beauty.contexts.identity.application.ports import ChallengeStatusReader
from beauty.contexts.identity.domain.auth_challenge import ChallengeStatus
from beauty.shared.application.cqrs import Handler, Query
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.secrets import HashedSecret


@dataclass(frozen=True, slots=True)
class GetChallengeStatus(Query[ChallengeStatusView]):
    """Статус входа для браузера, который его начал."""

    challenge_id: UUID
    browser_secret: str


class GetChallengeStatusHandler(Handler[GetChallengeStatus, ChallengeStatusView]):
    """Читает статус из read-модели и проверяет принадлежность браузеру.

    Чужому браузеру отвечаем «не найдено», а не «доступ запрещён»: так по id нельзя
    узнать, существует ли чужой вход.
    """

    def __init__(self, reader: ChallengeStatusReader, clock: Clock) -> None:
        """Получить зависимости."""
        self._reader = reader
        self._clock = clock

    async def handle(self, message: GetChallengeStatus) -> ChallengeStatusView:
        """Вернуть эффективный статус."""
        record = await self._reader.read(message.challenge_id)
        if record is None or not HashedSecret(record.browser_secret_digest).matches(message.browser_secret):
            raise ChallengeNotFoundError()
        status = ChallengeStatus(record.status)
        if status.is_in_progress and self._clock.now() >= record.expires_at:
            status = ChallengeStatus.EXPIRED
        return ChallengeStatusView(record.challenge_id, status.value, record.expires_at)
