"""Репозитории Identity на SQLAlchemy."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from beauty.contexts.identity.domain.auth_challenge import AuthChallenge, ChallengeStatus
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.client_session import ClientSession
from beauty.contexts.identity.domain.repositories import (
    AuthChallengeRepository,
    ClientAccountRepository,
    ClientSessionRepository,
)
from beauty.contexts.identity.domain.value_objects import AuthNonce, PhoneNumber, TelegramUserId
from beauty.contexts.identity.infrastructure.tables import auth_challenges, client_accounts
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyAuthChallengeRepository(SqlAlchemyRepository[AuthChallenge], AuthChallengeRepository):
    """Попытки входа."""

    async def get(self, challenge_id: UUID) -> AuthChallenge | None:
        """По первичному ключу (identity map сессии избавляет от повторного запроса)."""
        return self._seen(await self._session.get(AuthChallenge, challenge_id))

    async def get_by_nonce(self, nonce: AuthNonce) -> AuthChallenge | None:
        """По уникальному nonce."""
        statement = select(AuthChallenge).where(auth_challenges.c.nonce == nonce)
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())

    async def get_awaiting_contact(
        self, telegram_user: TelegramUserId, now: datetime
    ) -> AuthChallenge | None:
        """Последний подтверждённый неистёкший вход пользователя (частичный индекс)."""
        statement = (
            select(AuthChallenge)
            .where(
                auth_challenges.c.telegram_user_id == telegram_user,
                auth_challenges.c.status == ChallengeStatus.CONFIRMED,
                auth_challenges.c.expires_at > now,
            )
            .order_by(auth_challenges.c.created_at.desc())
            .limit(1)
        )
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())


class SqlAlchemyClientAccountRepository(SqlAlchemyRepository[ClientAccount], ClientAccountRepository):
    """Учётные записи клиентов."""

    async def get(self, account_id: UUID) -> ClientAccount | None:
        """По первичному ключу."""
        return self._seen(await self._session.get(ClientAccount, account_id))

    async def get_by_telegram_user(self, telegram_user: TelegramUserId) -> ClientAccount | None:
        """По уникальному Telegram id."""
        statement = select(ClientAccount).where(client_accounts.c.telegram_user_id == telegram_user)
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())

    async def get_by_phone(self, phone: PhoneNumber) -> ClientAccount | None:
        """По уникальному номеру."""
        statement = select(ClientAccount).where(client_accounts.c.phone == phone)
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())


class SqlAlchemyClientSessionRepository(SqlAlchemyRepository[ClientSession], ClientSessionRepository):
    """Сессии клиентов."""

    async def get(self, session_id: UUID) -> ClientSession | None:
        """По первичному ключу."""
        return self._seen(await self._session.get(ClientSession, session_id))
