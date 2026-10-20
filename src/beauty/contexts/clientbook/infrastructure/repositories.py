"""Репозиторий карточек клиентов на SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from beauty.contexts.clientbook.domain.client_file import ClientFile
from beauty.contexts.clientbook.domain.repositories import ClientFileRepository
from beauty.contexts.clientbook.infrastructure.tables import files
from beauty.shared.infrastructure.db.repository import SqlAlchemyRepository


class SqlAlchemyClientFileRepository(SqlAlchemyRepository[ClientFile], ClientFileRepository):
    """Карточки (заметки — вместе с карточкой)."""

    async def get(self, master_id: UUID, client_id: UUID) -> ClientFile | None:
        """По паре «мастер, клиент» (уникальный индекс)."""
        statement = select(ClientFile).where(files.c.master_id == master_id, files.c.client_id == client_id)
        return self._seen((await self._session.execute(statement)).scalar_one_or_none())
