"""Императивный маппинг переписок и сообщений."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.orm import composite

from beauty.contexts.conversations.domain.broadcast import Broadcast
from beauty.contexts.conversations.domain.conversation import ClientCard, Conversation
from beauty.contexts.conversations.domain.message import Message
from beauty.contexts.conversations.infrastructure.tables import broadcasts, conversations, messages
from beauty.shared.infrastructure.db.metadata import mapper_registry


class ConversationsOrmMapper:
    """Оба агрегата — с оптимистичной блокировкой (``version``)."""

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(
            Conversation,
            conversations,
            version_id_col=conversations.c.version,
            properties={
                "client": composite(
                    ClientCard, conversations.c.client_display_name, conversations.c.client_phone_masked
                )
            },
        )
        mapper_registry.map_imperatively(Message, messages, version_id_col=messages.c.version)
        mapper_registry.map_imperatively(Broadcast, broadcasts, version_id_col=broadcasts.c.version)
        cls._mapped = True
