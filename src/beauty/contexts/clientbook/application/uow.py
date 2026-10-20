"""Unit of Work контекста Clientbook."""

from __future__ import annotations

from beauty.contexts.clientbook.domain.repositories import ClientFileRepository
from beauty.shared.application.uow import UnitOfWork


class ClientbookUnitOfWork(UnitOfWork):
    """Карточки клиентов."""

    files: ClientFileRepository
