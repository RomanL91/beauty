"""Императивный маппинг профилей и тикетов."""

from __future__ import annotations

from typing import ClassVar

from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.ticket import RunTicket
from beauty.contexts.agent.infrastructure.tables import profiles, tickets
from beauty.shared.infrastructure.db.metadata import mapper_registry


class AgentOrmMapper:
    """Оба агрегата — с оптимистичной блокировкой."""

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(AgentProfile, profiles, version_id_col=profiles.c.version)
        mapper_registry.map_imperatively(RunTicket, tickets, version_id_col=tickets.c.version)
        cls._mapped = True
