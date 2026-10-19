"""Тестовые двойники: часы, генераторы, in-memory репозитории и Unit of Work."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from uuid import UUID

from beauty.contexts.identity.application.ports import SecretGenerator
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.contexts.identity.domain.auth_challenge import AuthChallenge, ChallengeStatus
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.client_session import ClientSession
from beauty.contexts.identity.domain.repositories import (
    AuthChallengeRepository,
    ClientAccountRepository,
    ClientSessionRepository,
)
from beauty.contexts.identity.domain.value_objects import AuthNonce, PhoneNumber, TelegramUserId
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.events import DomainEvent
from beauty.shared.infrastructure.db.tracker import AggregateTracker


class FrozenClock(Clock):
    """Управляемые часы."""

    def __init__(self, moment: datetime | None = None) -> None:
        """Зафиксировать момент."""
        self.moment = moment or datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        """Текущий зафиксированный момент."""
        return self.moment

    def advance(self, delta: timedelta) -> None:
        """Сдвинуть время вперёд."""
        self.moment += delta


class CountingSecretGenerator(SecretGenerator):
    """Детерминированные, но уникальные «секреты» допустимого формата."""

    def __init__(self) -> None:
        """Начать счётчик."""
        self._counter = itertools.count(1)

    def token(self, nbytes: int = 32) -> str:
        """Строка вида ``secret000001xxxx…`` (формат подходит и для nonce)."""
        return f"secret{next(self._counter):06d}" + "x" * nbytes


class IdentityStore:
    """Общее «хранилище» для in-memory репозиториев (переживает Unit of Work)."""

    def __init__(self) -> None:
        """Пустые коллекции."""
        self.challenges: dict[UUID, AuthChallenge] = {}
        self.accounts: dict[UUID, ClientAccount] = {}
        self.sessions: dict[UUID, ClientSession] = {}
        self.events: list[DomainEvent] = []
        self.commits = 0


class InMemoryChallenges(AuthChallengeRepository):
    """In-memory репозиторий попыток входа."""

    def __init__(self, store: IdentityStore, tracker: AggregateTracker) -> None:
        """Связать с хранилищем."""
        self._store, self._tracker = store, tracker

    def add(self, challenge: AuthChallenge) -> None:
        """Добавить."""
        self._store.challenges[challenge.id] = self._tracker.track(challenge)

    async def get(self, challenge_id: UUID) -> AuthChallenge | None:
        """По id."""
        found = self._store.challenges.get(challenge_id)
        return None if found is None else self._tracker.track(found)

    async def get_by_nonce(self, nonce: AuthNonce) -> AuthChallenge | None:
        """По nonce."""
        found = next((c for c in self._store.challenges.values() if c.nonce == nonce), None)
        return None if found is None else self._tracker.track(found)

    async def get_awaiting_contact(
        self, telegram_user: TelegramUserId, now: datetime
    ) -> AuthChallenge | None:
        """Последний подтверждённый."""
        candidates = [
            c
            for c in self._store.challenges.values()
            if c.telegram_user_id == telegram_user
            and c.status is ChallengeStatus.CONFIRMED
            and c.expires_at > now
        ]
        found = max(candidates, key=lambda c: c.created_at, default=None)
        return None if found is None else self._tracker.track(found)


class InMemoryAccounts(ClientAccountRepository):
    """In-memory репозиторий учётных записей."""

    def __init__(self, store: IdentityStore, tracker: AggregateTracker) -> None:
        """Связать с хранилищем."""
        self._store, self._tracker = store, tracker

    def add(self, account: ClientAccount) -> None:
        """Добавить."""
        self._store.accounts[account.id] = self._tracker.track(account)

    async def get(self, account_id: UUID) -> ClientAccount | None:
        """По id."""
        found = self._store.accounts.get(account_id)
        return None if found is None else self._tracker.track(found)

    async def get_by_telegram_user(self, telegram_user: TelegramUserId) -> ClientAccount | None:
        """По Telegram id."""
        found = next((a for a in self._store.accounts.values() if a.telegram_user_id == telegram_user), None)
        return None if found is None else self._tracker.track(found)

    async def get_by_phone(self, phone: PhoneNumber) -> ClientAccount | None:
        """По номеру."""
        found = next((a for a in self._store.accounts.values() if a.phone == phone), None)
        return None if found is None else self._tracker.track(found)


class InMemorySessions(ClientSessionRepository):
    """In-memory репозиторий сессий."""

    def __init__(self, store: IdentityStore, tracker: AggregateTracker) -> None:
        """Связать с хранилищем."""
        self._store, self._tracker = store, tracker

    def add(self, session: ClientSession) -> None:
        """Добавить."""
        self._store.sessions[session.id] = self._tracker.track(session)

    async def get(self, session_id: UUID) -> ClientSession | None:
        """По id."""
        found = self._store.sessions.get(session_id)
        return None if found is None else self._tracker.track(found)

    async def active_of(self, account_id: UUID) -> list[ClientSession]:
        """Неотозванные сессии учётной записи."""
        return [
            self._tracker.track(s)
            for s in self._store.sessions.values()
            if s.account_id == account_id and s.revoked_at is None
        ]


class InMemoryIdentityUnitOfWork(IdentityUnitOfWork):
    """Unit of Work поверх ``IdentityStore``: при коммите складывает события в хранилище."""

    def __init__(self, store: IdentityStore) -> None:
        """Связать с хранилищем."""
        self._store = store
        self._tracker = AggregateTracker()

    async def _begin(self) -> None:
        """Новые репозитории и трекер."""
        self._tracker = AggregateTracker()
        self.challenges = InMemoryChallenges(self._store, self._tracker)
        self.accounts = InMemoryAccounts(self._store, self._tracker)
        self.sessions = InMemorySessions(self._store, self._tracker)

    async def commit(self) -> None:
        """Зафиксировать события."""
        self._store.events.extend(self._tracker.collect_events())
        self._store.commits += 1

    async def rollback(self) -> None:
        """Откат in-memory не моделируется (тесты проверяют это на реальной БД)."""
