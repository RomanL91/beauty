"""Действия хозяина сервиса над мастерами и клиентами — через контексты-владельцы, с журналом."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.admin.application.dto import AdminActor
from beauty.contexts.admin.application.ports import MasterDraft, Platform, Report, Reports
from beauty.contexts.admin.application.uow import AdminUnitOfWork
from beauty.contexts.admin.domain.audit import AuditEntry
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.application.errors import NotFoundError
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

type UowFactory = Callable[[], AdminUnitOfWork]


class MasterNotFoundError(NotFoundError):
    """Мастера нет."""

    code = "master_not_found"


class ClientNotFoundError(NotFoundError):
    """Клиента нет."""

    code = "account_not_found"


class _Audited:
    """Общая часть: зависимости и запись в журнал."""

    def __init__(
        self, uow: UowFactory, platform: Platform, reports: Reports, clock: Clock, ids: IdGenerator
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._platform = platform
        self._reports = reports
        self._clock = clock
        self._ids = ids

    async def _audit(self, actor: AdminActor, action: str, target: str | None, summary: str) -> None:
        async with self._uow() as uow:
            uow.audit.add(
                AuditEntry(
                    self._ids.new(), actor.admin_id, actor.login, action, target, summary, self._clock.now()
                )
            )
            await uow.commit()

    async def _master(self, master_id: UUID) -> Report:
        found = await self._reports.master(master_id)
        if found is None:
            raise MasterNotFoundError()
        return found


@dataclass(frozen=True, slots=True)
class CreateMaster(Command[Report]):
    """Завести мастера: страница — черновик; владелец — если указан."""

    actor: AdminActor
    draft: MasterDraft


class CreateMasterHandler(_Audited, Handler[CreateMaster, Report]):
    """Регистрация в Tenancy."""

    async def handle(self, message: CreateMaster) -> Report:
        """Завести."""
        master_id = await self._platform.register_master(message.draft)
        owner = f", владелец {message.draft.owner_phone}" if message.draft.owner_phone else ""
        await self._audit(
            message.actor,
            "master.created",
            message.draft.slug,
            f"Завёл мастера {message.draft.display_name}{owner}",
        )
        return await self._master(master_id)


@dataclass(frozen=True, slots=True)
class SetMasterOwner(Command[Report]):
    """Сменить телефон владельца."""

    actor: AdminActor
    master_id: UUID
    phone: str


class SetMasterOwnerHandler(_Audited, Handler[SetMasterOwner, Report]):
    """Кабинет открывается новому номеру Telegram."""

    async def handle(self, message: SetMasterOwner) -> Report:
        """Сменить."""
        before = await self._master(message.master_id)
        await self._platform.set_owner(message.master_id, message.phone)
        after = await self._master(message.master_id)
        await self._audit(
            message.actor,
            "master.owner_changed",
            str(after["slug"]),
            f"Владелец: {before['owner_phone'] or '—'} → {after['owner_phone']}",
        )
        return after


@dataclass(frozen=True, slots=True)
class SetMasterPublication(Command[Report]):
    """Опубликовать или скрыть страницу."""

    actor: AdminActor
    master_id: UUID
    published: bool


class SetMasterPublicationHandler(_Audited, Handler[SetMasterPublication, Report]):
    """Публикация — по правилам Tenancy (нужны услуги и рабочие часы)."""

    async def handle(self, message: SetMasterPublication) -> Report:
        """Применить."""
        await self._master(message.master_id)
        await self._platform.set_published(message.master_id, message.published)
        after = await self._master(message.master_id)
        action, summary = (
            ("master.published", "Опубликовал страницу")
            if message.published
            else ("master.unpublished", "Скрыл страницу")
        )
        await self._audit(message.actor, action, str(after["slug"]), summary)
        return after


@dataclass(frozen=True, slots=True)
class SetMasterAgent(Command[Report]):
    """Включить или выключить ИИ-администратора мастера."""

    actor: AdminActor
    master_id: UUID
    enabled: bool


class SetMasterAgentHandler(_Audited, Handler[SetMasterAgent, Report]):
    """Профиль Hermes должен быть подключён (``beauty agent provision``)."""

    async def handle(self, message: SetMasterAgent) -> Report:
        """Применить."""
        await self._master(message.master_id)
        await self._platform.set_agent(message.master_id, message.enabled)
        after = await self._master(message.master_id)
        action = "agent.enabled" if message.enabled else "agent.disabled"
        summary = "Включил ИИ-администратора" if message.enabled else "Выключил ИИ-администратора"
        await self._audit(message.actor, action, str(after["slug"]), summary)
        return after


@dataclass(frozen=True, slots=True)
class SetMasterBroadcasts(Command[Report]):
    """Разрешить или запретить мастеру рассылки."""

    actor: AdminActor
    master_id: UUID
    allowed: bool


class SetMasterBroadcastsHandler(_Audited, Handler[SetMasterBroadcasts, Report]):
    """Запрет — в Conversations; уже идущая рассылка доставляется до конца."""

    async def handle(self, message: SetMasterBroadcasts) -> Report:
        """Применить."""
        await self._master(message.master_id)
        await self._platform.set_broadcasts(message.master_id, message.allowed)
        after = await self._master(message.master_id)
        action = "broadcasts.allowed" if message.allowed else "broadcasts.blocked"
        summary = "Разрешил рассылки" if message.allowed else "Запретил рассылки"
        await self._audit(message.actor, action, str(after["slug"]), summary)
        return after


@dataclass(frozen=True, slots=True)
class SetClientBlock(Command[Report]):
    """Заблокировать или разблокировать клиента."""

    actor: AdminActor
    client_id: UUID
    blocked: bool
    reason: str | None = None


class SetClientBlockHandler(_Audited, Handler[SetClientBlock, Report]):
    """Блокировка — в Identity (сессии отзываются)."""

    async def handle(self, message: SetClientBlock) -> Report:
        """Применить."""
        if await self._reports.client(message.client_id) is None:
            raise ClientNotFoundError()
        await self._platform.set_client_blocked(message.client_id, message.blocked, message.reason)
        after = await self._reports.client(message.client_id)
        assert after is not None
        if message.blocked:
            reason = f": {message.reason.strip()}" if message.reason and message.reason.strip() else ""
            await self._audit(
                message.actor, "client.blocked", str(after["phone"]), f"Заблокировал клиента{reason}"
            )
        else:
            await self._audit(message.actor, "client.unblocked", str(after["phone"]), "Разблокировал клиента")
        return after
