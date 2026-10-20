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
        "beauty.contexts.tenancy.infrastructure.tables",
        "beauty.contexts.booking.infrastructure.tables",
        "beauty.contexts.conversations.infrastructure.tables",
        "beauty.contexts.agent.infrastructure.tables",
        "beauty.contexts.notifications.infrastructure.tables",
        "beauty.contexts.admin.infrastructure.tables",
        "beauty.contexts.clientbook.infrastructure.tables",
    )
    SCHEMAS: tuple[str, ...] = (
        "infra",
        "identity",
        "tenancy",
        "booking",
        "conversations",
        "agent",
        "notifications",
        "admin",
        "clientbook",
    )

    @classmethod
    def load(cls) -> MetaData:
        """Импортировать модули таблиц и вернуть общий ``MetaData``."""
        for module in cls.TABLE_MODULES:
            importlib.import_module(module)
        return metadata
