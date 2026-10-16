"""Unit of Work, маппинг, оптимистичная блокировка и гонки на реальной БД."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from beauty.bootstrap.container import ApplicationContainer
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.value_objects import PhoneNumber, TelegramUserId
from beauty.contexts.identity.infrastructure.tables import auth_challenges, client_accounts
from beauty.contexts.identity.infrastructure.uow import SqlAlchemyIdentityUnitOfWork
from beauty.shared.application.errors import ConcurrencyConflictError
from beauty.shared.infrastructure.outbox.table import outbox_table
from tests.integration.helpers import BotSimulator

pytestmark = pytest.mark.integration


def make_uow(container: ApplicationContainer) -> SqlAlchemyIdentityUnitOfWork:
    """Новый Unit of Work Identity."""
    return SqlAlchemyIdentityUnitOfWork(container.session_factory, container.outbox_writer)


async def scalar(container: ApplicationContainer, statement: object) -> object:
    """Выполнить скалярный запрос."""
    async with container.session_factory() as session:
        return (await session.execute(statement)).scalar_one()  # type: ignore[call-overload]


async def test_login_persists_aggregates_and_events_atomically(container: ApplicationContainer) -> None:
    """Вход сохраняет учётную запись, статус входа и события в outbox одной транзакцией."""
    bot = BotSimulator(container.mediator)
    await bot.start_and_confirm(telegram_user=1001)
    await bot.share_contact(1001, "77011234567")

    async with make_uow(container) as uow:
        account = await uow.accounts.get_by_phone(PhoneNumber("+77011234567"))
        assert account is not None
        assert account.telegram_user_id == TelegramUserId(1001)
        assert account.version == 1, "регистрация и вход — один INSERT в одной транзакции"

    async with container.session_factory() as session:
        keys = (await session.execute(select(outbox_table.c.routing_key))).scalars().all()
    assert sorted(keys) == [
        "identity.auth_challenge.completed",
        "identity.client.authenticated",
        "identity.client.registered",
    ]


async def test_uncommitted_work_is_rolled_back(container: ApplicationContainer) -> None:
    """Исключение внутри Unit of Work — ничего не сохранено."""
    with pytest.raises(RuntimeError):
        async with make_uow(container) as uow:
            uow.accounts.add(
                ClientAccount.register(
                    account_id=uuid4(),
                    phone=PhoneNumber("+77010000000"),
                    telegram_user_id=TelegramUserId(5),
                    now=datetime.now(UTC),
                )
            )
            raise RuntimeError("сбой посреди сценария")
    assert await scalar(container, select(func.count()).select_from(client_accounts)) == 0
    assert await scalar(container, select(func.count()).select_from(outbox_table)) == 0


async def test_aggregate_read_without_commit_stays_readable(container: ApplicationContainer) -> None:
    """Агрегат, прочитанный в блоке без commit, читается и после выхода (откат его не «протухает»)."""
    started = await BotSimulator(container.mediator).start_and_confirm(telegram_user=1002)
    async with make_uow(container) as uow:
        challenge = await uow.challenges.get(started.challenge_id)
    assert challenge is not None
    assert challenge.id == started.challenge_id
    assert challenge.expires_at > container.clock.now() - timedelta(days=1)


async def test_optimistic_locking_detects_lost_update(container: ApplicationContainer) -> None:
    """Две транзакции меняют один агрегат: вторая получает конфликт, а не затирает первую."""
    bot = BotSimulator(container.mediator)
    started = await bot.start_and_confirm(telegram_user=1001)
    now = container.clock.now()

    first, second = make_uow(container), make_uow(container)
    async with first, second:
        a = await first.challenges.get(started.challenge_id)
        b = await second.challenges.get(started.challenge_id)
        assert a is not None
        assert b is not None
        a.expires_at = now + timedelta(minutes=1)
        b.expires_at = now + timedelta(minutes=2)
        await first.commit()
        with pytest.raises(ConcurrencyConflictError):
            await second.commit()


async def test_parallel_logins_of_new_client_are_resolved_by_retry(container: ApplicationContainer) -> None:
    """Новый клиент одновременно входит с двух устройств.

    Обе транзакции пытаются зарегистрировать учётную запись; уникальный индекс
    отклоняет вторую, медиатор повторяет команду, и при повторе цепочка находит
    уже созданную запись. Итог — одна учётная запись и оба входа завершены.
    """
    bot = BotSimulator(container.mediator)
    first = await bot.start_and_confirm(telegram_user=4242)
    second = await bot.start_and_confirm(telegram_user=4242)

    await asyncio.gather(bot.share_contact(4242, "77017777777"), bot.share_contact(4242, "77017777777"))

    assert await scalar(container, select(func.count()).select_from(client_accounts)) == 1
    async with container.session_factory() as session:
        statuses = (
            await session.execute(
                select(auth_challenges.c.status).where(
                    auth_challenges.c.id.in_([first.challenge_id, second.challenge_id])
                )
            )
        ).scalars()
        assert sorted(status.value for status in statuses) == ["completed", "completed"]


async def test_awaiting_contact_query_uses_partial_index(container: ApplicationContainer) -> None:
    """План запроса «вход, ждущий контакт» идёт по частичному индексу."""
    async with container.engine.connect() as connection:
        await connection.execute(text("SET enable_seqscan = off"))
        plan = (
            (
                await connection.execute(
                    text(
                        "EXPLAIN SELECT * FROM identity.auth_challenges "
                        "WHERE telegram_user_id = 1 AND status = 'confirmed' AND expires_at > now() "
                        "ORDER BY created_at DESC LIMIT 1"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert any("ix_auth_challenges_awaiting_contact" in line for line in plan)
