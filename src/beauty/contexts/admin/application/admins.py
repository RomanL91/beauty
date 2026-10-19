"""Администраторы: список, добавить, включить/отключить, задать пароль; первый — из CLI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from beauty.contexts.admin.application.dto import AdminActor, AdminView
from beauty.contexts.admin.application.errors import (
    AdminLoginTakenError,
    AdminNotFoundError,
    CannotDisableSelfError,
)
from beauty.contexts.admin.application.uow import AdminUnitOfWork
from beauty.contexts.admin.domain.admin import Administrator, normalize_login
from beauty.contexts.admin.domain.audit import AuditEntry
from beauty.contexts.admin.domain.passwords import hash_password
from beauty.shared.application.cqrs import Command, Handler, Query
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

type UowFactory = Callable[[], AdminUnitOfWork]


@dataclass(frozen=True, slots=True)
class ListAdmins(Query[list[AdminView]]):
    """Все администраторы."""


class ListAdminsHandler(Handler[ListAdmins, list[AdminView]]):
    """По логину."""

    def __init__(self, uow: UowFactory) -> None:
        """Получить UoW."""
        self._uow = uow

    async def handle(self, message: ListAdmins) -> list[AdminView]:
        """Список."""
        async with self._uow() as uow:
            return [AdminView.of(a) for a in await uow.admins.all()]


@dataclass(frozen=True, slots=True)
class CreateAdmin(Command[AdminView]):
    """Добавить администратора; ``actor=None`` — из командной строки (первый)."""

    actor: AdminActor | None
    login: str
    display_name: str
    password: str


class CreateAdminHandler(Handler[CreateAdmin, AdminView]):
    """Логин уникален."""

    def __init__(self, uow: UowFactory, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: CreateAdmin) -> AdminView:
        """Добавить."""
        password_hash = await asyncio.to_thread(hash_password, message.password)
        now = self._clock.now()
        admin = Administrator.register(
            admin_id=self._ids.new(),
            login=message.login,
            display_name=message.display_name,
            password_hash=password_hash,
            now=now,
        )
        async with self._uow() as uow:
            if await uow.admins.by_login(admin.login) is not None:
                raise AdminLoginTakenError(f"Логин {admin.login} занят")
            uow.admins.add(admin)
            if message.actor is not None:
                uow.audit.add(
                    AuditEntry(
                        self._ids.new(),
                        message.actor.admin_id,
                        message.actor.login,
                        "admin.created",
                        admin.login,
                        f"Добавил администратора {admin.display_name}",
                        now,
                    )
                )
            await uow.commit()
        return AdminView.of(admin)


@dataclass(frozen=True, slots=True)
class UpdateAdmin(Command[AdminView]):
    """Включить/отключить или задать пароль другому администратору."""

    actor: AdminActor
    admin_id: UUID
    active: bool | None = None
    password: str | None = None


class UpdateAdminHandler(Handler[UpdateAdmin, AdminView]):
    """Отключение и новый пароль закрывают сессии администратора (кроме текущей своей)."""

    def __init__(self, uow: UowFactory, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: UpdateAdmin) -> AdminView:
        """Применить."""
        if message.active is False and message.admin_id == message.actor.admin_id:
            raise CannotDisableSelfError("Себя отключить нельзя")
        new_hash = (
            None if message.password is None else await asyncio.to_thread(hash_password, message.password)
        )
        now = self._clock.now()
        async with self._uow() as uow:
            admin = await uow.admins.get(message.admin_id)
            if admin is None:
                raise AdminNotFoundError()
            changes = []
            if message.active is not None and admin.set_active(message.active, now):
                changes.append("включил" if message.active else "отключил")
            if new_hash is not None:
                admin.change_password(new_hash, now)
                changes.append("задал пароль")
            if changes:
                for session in await uow.sessions.active_of(admin.id):
                    if session.id != message.actor.session_id:
                        session.revoke(now)
                uow.audit.add(
                    AuditEntry(
                        self._ids.new(),
                        message.actor.admin_id,
                        message.actor.login,
                        "admin.updated",
                        admin.login,
                        f"Администратор {admin.login}: {', '.join(changes)}",
                        now,
                    )
                )
            await uow.commit()
        return AdminView.of(admin)


@dataclass(frozen=True, slots=True)
class ResetAdminPassword(Command[AdminView]):
    """Задать пароль из командной строки (забыли пароль); учётная запись включается."""

    login: str
    password: str


class ResetAdminPasswordHandler(Handler[ResetAdminPassword, AdminView]):
    """Сессии администратора закрываются."""

    def __init__(self, uow: UowFactory, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: ResetAdminPassword) -> AdminView:
        """Сбросить."""
        new_hash = await asyncio.to_thread(hash_password, message.password)
        now = self._clock.now()
        async with self._uow() as uow:
            admin = await uow.admins.by_login(normalize_login(message.login))
            if admin is None:
                raise AdminNotFoundError()
            admin.change_password(new_hash, now)
            admin.set_active(True, now)
            for session in await uow.sessions.active_of(admin.id):
                session.revoke(now)
            await uow.commit()
        return AdminView.of(admin)
