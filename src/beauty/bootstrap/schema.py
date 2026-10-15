"""Каталог схемы БД для миграций.

Таблицы регистрируются в общем ``MetaData`` при импорте модулей. Каталог
импортирует все модули с таблицами, чтобы Alembic видел полную схему.
"""

from __future__ import annotations

import importlib

from sqlalchemy import MetaData

from beauty.shared.infrastructure.db.metadata import metadata


class SchemaCatalog:
    """Загружает определения таблиц всех контекстов."""

    TABLE_MODULES: tuple[str, ...] = (
        "beauty.shared.infrastructure.outbox.table",
        "beauty.shared.infrastructure.inbox.table",
        "beauty.shared.infrastructure.scheduling.table",
        "beauty.contexts.identity.infrastructure.tables",
    )
    SCHEMAS: tuple[str, ...] = ("infra", "identity")

    @classmethod
    def load(cls) -> MetaData:
        """Импортировать модули таблиц и вернуть общий ``MetaData``."""
        for module in cls.TABLE_MODULES:
            importlib.import_module(module)
        return metadata
