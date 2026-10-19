"""Сценарий: хозяин сервиса блокирует или разблокирует клиента."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.identity.application.errors import AccountNotFoundError
from beauty.contexts.identity.application.uow import IdentityUnitOfWork
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class SetAccountBlocked(Command[bool]):
    """Заблокировать (с причиной) или разблокировать; ``True`` — состояние изменилось."""

    account_id: UUID
    blocked: bool
    reason: str | None = None


class SetAccountBlockedHandler(Handler[SetAccountBlocked, bool]):
    """Блокировка отзывает все сессии: вход и обновление сессии дальше запрещены.

    Выданный access-токен доживает свой короткий срок (``BEAUTY_AUTH__ACCESS_TTL``).
    """

    def __init__(self, uow: IdentityUnitOfWork, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: SetAccountBlocked) -> bool:
        """Применить."""
        now = self._clock.now()
        async with self._uow as uow:
            account = await uow.accounts.get(message.account_id)
            if account is None:
                raise AccountNotFoundError()
            if not message.blocked:
                changed = account.unblock(now)
            else:
                changed = account.block(message.reason, now)
                for session in await uow.sessions.active_of(account.id):
                    session.revoke(now, "account_blocked")
            await uow.commit()
        return changed
