"""Императивный маппинг Admin."""

from __future__ import annotations

from typing import ClassVar

from beauty.contexts.admin.domain.admin import Administrator
from beauty.contexts.admin.domain.audit import AuditEntry
from beauty.contexts.admin.domain.session import AdminSession
from beauty.contexts.admin.infrastructure.tables import administrators, audit, sessions
from beauty.shared.infrastructure.db.metadata import mapper_registry


class AdminOrmMapper:
    """Администраторы и сессии — с оптимистичной блокировкой; журнал — только добавляется."""

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(
            Administrator, administrators, version_id_col=administrators.c.version
        )
        mapper_registry.map_imperatively(AdminSession, sessions, version_id_col=sessions.c.version)
        mapper_registry.map_imperatively(AuditEntry, audit, version_id_col=audit.c.version)
        cls._mapped = True
