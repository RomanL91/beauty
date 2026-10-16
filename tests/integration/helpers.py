"""Помощники интеграционных тестов: вход через медиатор, доставка событий без брокера."""

from __future__ import annotations

from collections.abc import Mapping

import httpx
from sqlalchemy import func, select, update

from beauty.bootstrap.container import ApplicationContainer
from beauty.contexts.identity.application.commands import (
    ClaimChallenge,
    CompleteChallengeWithContact,
    ConfirmChallengeCode,
    StartTelegramAuth,
)
from beauty.contexts.identity.application.dto import StartedChallenge
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.inbox.guard import (
    InboxClaimFirstHandler,
    InboxGuard,
    InboxIdempotentHandler,
)
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.outbox.table import outbox_table
from beauty.shared.infrastructure.realtime.bridge import RealtimeBridge


class BotSimulator:
    """Действия пользователя в Telegram-боте, выраженные командами медиатора."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    @staticmethod
    def nonce_of(deep_link: str) -> str:
        """Параметр ``start`` из deep link."""
        return deep_link.rsplit("start=", 1)[1]

    async def confirm(self, deep_link: str, code: str, telegram_user: int) -> None:
        """Открыть ссылку и выбрать код."""
        nonce = self.nonce_of(deep_link)
        await self._mediator.send(ClaimChallenge(nonce, telegram_user))
        await self._mediator.send(ConfirmChallengeCode(nonce, telegram_user, code))

    async def share_contact(self, telegram_user: int, phone: str) -> None:
        """Поделиться своим контактом."""
        await self._mediator.send(CompleteChallengeWithContact(telegram_user, telegram_user, phone))

    async def start_and_confirm(self, telegram_user: int) -> StartedChallenge:
        """Начать вход (как браузер) и подтвердить код (как бот)."""
        started = await self._mediator.send(StartTelegramAuth())
        await self.confirm(started.deep_link, started.confirmation_code, telegram_user)
        return started


class EventPump:
    """Relay и консьюмеры без брокера: события outbox → обработчики подписок и realtime-хаб.

    Обработчики обёрнуты в inbox, как в процессе ``worker`` (долгие — claim-first, без общей
    транзакции); события, порождённые
    обработчиками, доставляются в следующих раундах.
    """

    def __init__(
        self, container: ApplicationContainer, overrides: Mapping[str, IntegrationEventHandler] | None = None
    ) -> None:
        """Собрать подписки контейнера; ``overrides`` — обработчики очередей вместо штатных."""
        self._container = container
        guard = InboxGuard()
        replaced = dict(overrides or {})
        self._handlers: list[tuple[tuple[str, ...], IntegrationEventHandler]] = []
        for subscription in container.event_subscriptions():
            name = subscription.spec.name
            handler = replaced.get(name, subscription.handler)
            guarded: IntegrationEventHandler = (
                InboxIdempotentHandler(handler, container.transaction_scope, guard, name)
                if subscription.ambient_transaction
                else InboxClaimFirstHandler(handler, container.session_factory, guard, name)
            )
            self._handlers.append((subscription.spec.binding_keys, guarded))
        self._bridge = RealtimeBridge(container.realtime_hub, container.realtime_resolvers())
        self.delivered: list[str] = []

    async def drain(self, rounds: int = 10) -> list[str]:
        """Доставлять, пока outbox не опустеет; вернуть ключи доставленных событий."""
        for _ in range(rounds):
            async with self._container.engine.begin() as connection:
                rows = (
                    await connection.execute(
                        select(outbox_table)
                        .where(outbox_table.c.published_at.is_(None))
                        .order_by(outbox_table.c.id)
                    )
                ).all()
                await connection.execute(
                    update(outbox_table)
                    .where(outbox_table.c.id.in_([row.id for row in rows]))
                    .values(published_at=func.now())
                )
            if not rows:
                return self.delivered
            for row in rows:
                envelope = EventEnvelope(
                    message_id=row.id,
                    routing_key=row.routing_key,
                    event_type=row.event_type,
                    event_version=row.event_version,
                    occurred_at=row.occurred_at,
                    payload=row.payload,
                )
                self.delivered.append(envelope.routing_key)
                for keys, handler in self._handlers:
                    if any(_matches(key, envelope.routing_key) for key in keys):
                        await handler.handle(envelope)
                await self._bridge.handle(envelope)
        raise AssertionError("События продолжают порождаться — вероятен цикл")


def _matches(pattern: str, key: str) -> bool:
    """Шаблон topic-exchange (``*`` — одно слово; ``#`` в тестах не нужен)."""
    words, parts = pattern.split("."), key.split(".")
    return len(words) == len(parts) and all(w in ("*", p) for w, p in zip(words, parts, strict=True))


async def login(client: httpx.AsyncClient, mediator: Mediator, telegram_user: int, phone: str) -> str:
    """Войти через Telegram (бот — командами) и вернуть access-токен."""
    started = (await client.post("/api/v1/auth/telegram/challenges")).json()
    bot = BotSimulator(mediator)
    await bot.confirm(started["deep_link"], started["confirmation_code"], telegram_user)
    await bot.share_contact(telegram_user, phone)
    session = await client.post(f"/api/v1/auth/telegram/challenges/{started['challenge_id']}/session")
    token: str = session.json()["access_token"]
    return token
