"""Императивный маппинг профилей и тикетов."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.orm import relationship

from beauty.contexts.agent.domain.office import OfficeMessage
from beauty.contexts.agent.domain.playbook import Playbook, Practice
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.run import AgentRun
from beauty.contexts.agent.domain.ticket import RunTicket
from beauty.contexts.agent.infrastructure.tables import (
    office_messages,
    playbooks,
    practices,
    profiles,
    runs,
    tickets,
)
from beauty.shared.infrastructure.db.metadata import mapper_registry


class AgentOrmMapper:
    """Все агрегаты — с оптимистичной блокировкой."""

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(AgentProfile, profiles, version_id_col=profiles.c.version)
        mapper_registry.map_imperatively(RunTicket, tickets, version_id_col=tickets.c.version)
        mapper_registry.map_imperatively(AgentRun, runs)
        mapper_registry.map_imperatively(
            OfficeMessage, office_messages, version_id_col=office_messages.c.version
        )
        # Опыт с записями — один агрегат: правка записи трогает ``updated_at`` опыта — версия растёт.
        mapper_registry.map_imperatively(Practice, practices)
        mapper_registry.map_imperatively(
            Playbook,
            playbooks,
            version_id_col=playbooks.c.version,
            properties={
                "practices": relationship(
                    Practice, cascade="all, delete-orphan", order_by=practices.c.created_at, lazy="selectin"
                )
            },
        )
        cls._mapped = True
