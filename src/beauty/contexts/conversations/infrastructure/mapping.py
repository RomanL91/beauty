"""Императивный маппинг переписок и сообщений."""

from __future__ import annotations

from typing import ClassVar

from beauty.contexts.conversations.domain.conversation import Conversation
from beauty.contexts.conversations.domain.message import Message
from beauty.contexts.conversations.infrastructure.tables import conversations, messages
from beauty.shared.infrastructure.db.metadata import mapper_registry


class ConversationsOrmMapper:
    """Оба агрегата — с оптимистичной блокировкой (``version``)."""

    _mapped: ClassVar[bool] = False

    @classmethod
    def map(cls) -> None:
        """Выполнить маппинг идемпотентно."""
        if cls._mapped:
            return
        mapper_registry.map_imperatively(Conversation, conversations, version_id_col=conversations.c.version)
        mapper_registry.map_imperatively(Message, messages, version_id_col=messages.c.version)
        cls._mapped = True
