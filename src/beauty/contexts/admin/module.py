"""Модуль контекста Admin: админ-панель хозяина сервиса."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.admin.application.admins import (
    CreateAdmin,
    CreateAdminHandler,
    ListAdmins,
    ListAdminsHandler,
    ResetAdminPassword,
    ResetAdminPasswordHandler,
    UpdateAdmin,
    UpdateAdminHandler,
)
from beauty.contexts.admin.application.auth import (
    AdminLogin,
    AdminLoginHandler,
    AdminLogout,
    AdminLogoutHandler,
    AuthenticateAdmin,
    AuthenticateAdminHandler,
    ChangeOwnPassword,
    ChangeOwnPasswordHandler,
)
from beauty.contexts.admin.application.operations import (
    CreateMaster,
    CreateMasterHandler,
    SetClientBlock,
    SetClientBlockHandler,
    SetMasterAgent,
    SetMasterAgentHandler,
    SetMasterOwner,
    SetMasterOwnerHandler,
    SetMasterPublication,
    SetMasterPublicationHandler,
)
from beauty.contexts.admin.application.ports import Platform, Reports
from beauty.contexts.admin.application.queries import (
    AdminReport,
    AdminReportHandler,
    ListAudit,
    ListAuditHandler,
)
from beauty.contexts.admin.infrastructure.mapping import AdminOrmMapper
from beauty.contexts.admin.infrastructure.uow import SqlAlchemyAdminUnitOfWork
from beauty.contexts.admin.presentation.api import admin_router
from beauty.shared.application.mediator import Mediator
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.web.errors import HttpErrorMapper

_HTTP_STATUSES: dict[str, int] = {
    "invalid_credentials": 401,
    "admin_unauthorized": 401,
    "admin_locked": 429,
    "csrf_failed": 403,
    "wrong_password": 403,
    "admin_login_taken": 409,
    "cannot_disable_self": 409,
    "admin_not_found": 404,
    "weak_password": 422,
    "invalid_admin_login": 422,
    "invalid_admin_name": 422,
}


@dataclass(frozen=True, slots=True)
class AdminDependencies:
    """Зависимости панели."""

    session_factory: async_sessionmaker[AsyncSession]
    outbox_writer: OutboxWriter
    clock: Clock
    ids: IdGenerator
    platform: Platform
    reports: Reports
    session_ttl: timedelta
    secure_cookie: bool
    api_prefix: str


class AdminModule:
    """Сборка контекста Admin."""

    def __init__(self, dependencies: AdminDependencies) -> None:
        """Создать долгоживущие компоненты."""
        AdminOrmMapper.map()
        self._deps = dependencies

    def register(self, mediator: Mediator, http_errors: HttpErrorMapper) -> None:
        """Зарегистрировать обработчики и коды ошибок."""
        deps = self._deps
        uow, clock, ids = self._uow, deps.clock, deps.ids
        audited = (uow, deps.platform, deps.reports, clock, ids)
        mediator.register(AdminLogin, lambda: AdminLoginHandler(uow, clock, ids, deps.session_ttl))
        mediator.register(AuthenticateAdmin, lambda: AuthenticateAdminHandler(uow, clock))
        mediator.register(AdminLogout, lambda: AdminLogoutHandler(uow, clock))
        mediator.register(ChangeOwnPassword, lambda: ChangeOwnPasswordHandler(uow, clock, ids))
        mediator.register(ListAdmins, lambda: ListAdminsHandler(uow))
        mediator.register(CreateAdmin, lambda: CreateAdminHandler(uow, clock, ids))
        mediator.register(UpdateAdmin, lambda: UpdateAdminHandler(uow, clock, ids))
        mediator.register(ResetAdminPassword, lambda: ResetAdminPasswordHandler(uow, clock))
        mediator.register(CreateMaster, lambda: CreateMasterHandler(*audited))
        mediator.register(SetMasterOwner, lambda: SetMasterOwnerHandler(*audited))
        mediator.register(SetMasterPublication, lambda: SetMasterPublicationHandler(*audited))
        mediator.register(SetMasterAgent, lambda: SetMasterAgentHandler(*audited))
        mediator.register(SetClientBlock, lambda: SetClientBlockHandler(*audited))
        mediator.register(AdminReport, lambda: AdminReportHandler(deps.reports))
        mediator.register(ListAudit, lambda: ListAuditHandler(uow))
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def api_router(self, mediator: Mediator) -> APIRouter:
        """``/admin`` — панель."""
        deps = self._deps
        return admin_router(mediator, deps.api_prefix, deps.session_ttl, deps.secure_cookie)

    def _uow(self) -> SqlAlchemyAdminUnitOfWork:
        """Новый Unit of Work."""
        return SqlAlchemyAdminUnitOfWork(self._deps.session_factory, self._deps.outbox_writer)
