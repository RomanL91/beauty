"""Репозитории Admin на SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from beauty.contexts.admin.domain.admin import Administrator
from beauty.contexts.admin.domain.audit import AuditEntry
from beauty.contexts.admin.domain.repositories import (
    AdministratorRepository,
    AdminSessionRepository,
    AuditRepository,
)
from beauty.contexts.admin.domain.session import AdminSession
from beauty.contexts.admin.infrastructure.tables import administrators, audit, sessions
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyAdministratorRepository(SqlAlchemyRepository[Administrator], AdministratorRepository):
    """Администраторы."""

    async def get(self, admin_id: UUID) -> Administrator | None:
        """По id."""
        return self._seen(await self._session.get(Administrator, admin_id))

    async def by_login(self, login: str) -> Administrator | None:
        """По логину."""
        statement = select(Administrator).where(administrators.c.login == login)
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())

    async def all(self) -> list[Administrator]:
        """Все."""
        statement = select(Administrator).order_by(administrators.c.login)
        found = list((await self._session.execute(statement)).scalars())
        for admin in found:
            self._seen(admin)
        return found


class SqlAlchemyAdminSessionRepository(SqlAlchemyRepository[AdminSession], AdminSessionRepository):
    """Сессии."""

    async def get(self, session_id: UUID) -> AdminSession | None:
        """По id."""
        return self._seen(await self._session.get(AdminSession, session_id))

    async def active_of(self, admin_id: UUID) -> list[AdminSession]:
        """Неотозванные."""
        statement = select(AdminSession).where(
            sessions.c.admin_id == admin_id, sessions.c.revoked_at.is_(None)
        )
        found = list((await self._session.execute(statement)).scalars())
        for session in found:
            self._seen(session)
        return found


class SqlAlchemyAuditRepository(SqlAlchemyRepository[AuditEntry], AuditRepository):
    """Журнал действий."""

    async def page(self, before: UUID | None, limit: int) -> list[AuditEntry]:
        """Новые сверху (UUIDv7 растёт со временем)."""
        statement = select(AuditEntry).order_by(audit.c.id.desc()).limit(limit)
        if before is not None:
            statement = statement.where(audit.c.id < before)
        return list((await self._session.execute(statement)).scalars())
