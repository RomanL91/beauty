"""Вход администратора: логин и пароль → сессия; проверка сессии и CSRF; выход; смена пароля."""

from __future__ import annotations

import asyncio
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from beauty.contexts.admin.application.dto import AdminActor, AdminPrincipal, AdminView, LoginResult
from beauty.contexts.admin.application.errors import (
    AdminLockedError,
    AdminUnauthorizedError,
    CsrfFailedError,
    InvalidCredentialsError,
    WrongPasswordError,
)
from beauty.contexts.admin.application.uow import AdminUnitOfWork
from beauty.contexts.admin.domain.admin import normalize_login
from beauty.contexts.admin.domain.audit import AuditEntry
from beauty.contexts.admin.domain.passwords import DUMMY_HASH, hash_password, verify_password
from beauty.contexts.admin.domain.session import AdminSession
from beauty.shared.application.cqrs import Command, Handler, Query
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

type UowFactory = Callable[[], AdminUnitOfWork]


async def _verify(password: str, encoded: str) -> bool:
    """scrypt — в потоке: не держим цикл событий ~50 мс."""
    return await asyncio.to_thread(verify_password, password, encoded)


@dataclass(frozen=True, slots=True)
class AdminLogin(Command[LoginResult]):
    """Вход по логину и паролю."""

    login: str
    password: str


class AdminLoginHandler(Handler[AdminLogin, LoginResult]):
    """Неверный логин и неверный пароль неотличимы (и по ответу, и по времени)."""

    def __init__(self, uow: UowFactory, clock: Clock, ids: IdGenerator, session_ttl: timedelta) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._ttl = session_ttl

    async def handle(self, message: AdminLogin) -> LoginResult:
        """Проверить пароль, открыть сессию."""
        now = self._clock.now()
        async with self._uow() as uow:
            admin = await uow.admins.by_login(normalize_login(message.login))
            if admin is None or not admin.active:
                await _verify(message.password, DUMMY_HASH)
                raise InvalidCredentialsError()
            if admin.locked(now):
                raise AdminLockedError("Слишком много неверных паролей — попробуйте через 15 минут")
            if not await _verify(message.password, admin.password_hash):
                admin.login_failed(now)
                await uow.commit()
                if admin.locked(now):
                    raise AdminLockedError("Слишком много неверных паролей — попробуйте через 15 минут")
                raise InvalidCredentialsError()
            admin.logged_in(now)
            secret = secrets.token_urlsafe(32)
            session = AdminSession.open(
                session_id=self._ids.new(),
                admin_id=admin.id,
                secret=secret,
                csrf_token=secrets.token_urlsafe(24),
                now=now,
                ttl=self._ttl,
            )
            uow.sessions.add(session)
            await uow.commit()
        principal = AdminPrincipal(AdminView.of(admin), session.id, session.csrf_token, session.expires_at)
        return LoginResult(principal, f"{session.id}.{secret}")


@dataclass(frozen=True, slots=True)
class AuthenticateAdmin(Query[AdminPrincipal]):
    """Сессия по cookie; ``csrf`` — для изменяющих запросов (``None`` — не проверять)."""

    cookie: str | None
    csrf: str | None = None
    require_csrf: bool = False


class AuthenticateAdminHandler(Handler[AuthenticateAdmin, AdminPrincipal]):
    """Сессия жива, администратор активен, CSRF совпал."""

    def __init__(self, uow: UowFactory, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: AuthenticateAdmin) -> AdminPrincipal:
        """Проверить."""
        session_id, _, secret = (message.cookie or "").partition(".")
        try:
            parsed = UUID(session_id)
        except ValueError as error:
            raise AdminUnauthorizedError() from error
        async with self._uow() as uow:
            session = await uow.sessions.get(parsed)
            if session is None or not session.valid(secret, self._clock.now()):
                raise AdminUnauthorizedError()
            admin = await uow.admins.get(session.admin_id)
            if admin is None or not admin.active:
                raise AdminUnauthorizedError()
        if message.require_csrf and not hmac.compare_digest(message.csrf or "", session.csrf_token):
            raise CsrfFailedError()
        return AdminPrincipal(AdminView.of(admin), session.id, session.csrf_token, session.expires_at)


@dataclass(frozen=True, slots=True)
class AdminLogout(Command[None]):
    """Закрыть сессию."""

    session_id: UUID


class AdminLogoutHandler(Handler[AdminLogout, None]):
    """Отзывает сессию."""

    def __init__(self, uow: UowFactory, clock: Clock) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock

    async def handle(self, message: AdminLogout) -> None:
        """Отозвать."""
        async with self._uow() as uow:
            session = await uow.sessions.get(message.session_id)
            if session is not None:
                session.revoke(self._clock.now())
                await uow.commit()


@dataclass(frozen=True, slots=True)
class ChangeOwnPassword(Command[None]):
    """Сменить свой пароль: остальные сессии закрываются, текущая остаётся."""

    actor: AdminActor
    current_password: str
    new_password: str


class ChangeOwnPasswordHandler(Handler[ChangeOwnPassword, None]):
    """Нужен верный текущий пароль."""

    def __init__(self, uow: UowFactory, clock: Clock, ids: IdGenerator) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._clock = clock
        self._ids = ids

    async def handle(self, message: ChangeOwnPassword) -> None:
        """Сменить."""
        new_hash = await asyncio.to_thread(hash_password, message.new_password)
        now = self._clock.now()
        async with self._uow() as uow:
            admin = await uow.admins.get(message.actor.admin_id)
            if admin is None:
                raise AdminUnauthorizedError()
            if not await _verify(message.current_password, admin.password_hash):
                raise WrongPasswordError("Текущий пароль неверен")
            admin.change_password(new_hash, now)
            for session in await uow.sessions.active_of(admin.id):
                if session.id != message.actor.session_id:
                    session.revoke(now)
            uow.audit.add(
                AuditEntry(
                    self._ids.new(),
                    admin.id,
                    admin.login,
                    "admin.password_changed",
                    admin.login,
                    "Сменил свой пароль",
                    now,
                )
            )
            await uow.commit()
