"""Репозиторий мастеров на SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from beauty.contexts.tenancy.domain.master import Master
from beauty.contexts.tenancy.domain.repositories import MasterRepository
from beauty.contexts.tenancy.domain.value_objects import MasterSlug
from beauty.contexts.tenancy.infrastructure.tables import masters
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyMasterRepository(SqlAlchemyRepository[Master], MasterRepository):
    """Мастера (услуги подгружаются вместе с агрегатом)."""

    async def get(self, master_id: UUID) -> Master | None:
        """По первичному ключу."""
        return self._seen(await self._session.get(Master, master_id))

    async def get_by_slug(self, slug: MasterSlug) -> Master | None:
        """По уникальному адресу страницы."""
        statement = select(Master).where(masters.c.slug == slug)
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())
