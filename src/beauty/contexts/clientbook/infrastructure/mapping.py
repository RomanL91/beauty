"""Императивный маппинг Clientbook."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.orm import relationship

from beauty.contexts.clientbook.domain.client_file import ClientFile, ClientNote
from beauty.contexts.clientbook.infrastructure.tables import files, notes
from beauty.shared.infrastructure.db.metadata import mapper_registry


class ClientbookOrmMapper:
    """Карточка с заметками — один агрегат: заметки грузятся вместе с ним (``selectin``),
    удалённая из списка заметка удаляет строку. Любое изменение трогает ``updated_at``
    карточки — так версия растёт и при правке одних заметок."""

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(ClientNote, notes)
        mapper_registry.map_imperatively(
            ClientFile,
            files,
            version_id_col=files.c.version,
            properties={
                "notes": relationship(
                    ClientNote, cascade="all, delete-orphan", order_by=notes.c.created_at, lazy="selectin"
                )
            },
        )
        cls._mapped = True
