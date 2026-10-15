"""Read-модели Identity (SQL → DTO без агрегатов)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.identity.application.ports import ChallengeStatusReader, ChallengeStatusRecord
from beauty.contexts.identity.infrastructure.tables import auth_challenges


class SqlChallengeStatusReader(ChallengeStatusReader):
    """Читает четыре колонки по первичному ключу — без загрузки агрегата и трекинга.

    SSE-стрим опрашивает статус раз в несколько секунд как страховку от потерянного
    realtime-события, поэтому запрос должен быть максимально дешёвым.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Получить фабрику сессий."""
        self._session_factory = session_factory

    async def read(self, challenge_id: UUID) -> ChallengeStatusRecord | None:
        """Прочитать статус."""
        statement = select(
            auth_challenges.c.id,
            auth_challenges.c.status,
            auth_challenges.c.expires_at,
            auth_challenges.c.browser_secret_digest,
        ).where(auth_challenges.c.id == challenge_id)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        return ChallengeStatusRecord(
            challenge_id=row.id,
            status=row.status.value,
            expires_at=row.expires_at,
            browser_secret_digest=row.browser_secret_digest.digest,
        )
