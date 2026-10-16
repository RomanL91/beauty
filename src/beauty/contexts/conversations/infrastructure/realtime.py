"""Realtime-топики Conversations: «в ленте новое событие»."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from beauty.contexts.conversations.domain.events import FeedAppended
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.realtime.bridge import TopicResolver


class FeedTopic:
    """Имя топика ленты переписки."""

    PREFIX = "conversations.feed"

    @classmethod
    def of(cls, conversation_id: UUID | str) -> str:
        """Топик переписки."""
        return f"{cls.PREFIX}:{conversation_id}"


class FeedTopicResolver(TopicResolver):
    """Будит потоки переписки; само сообщение поток читает из журнала (с проверкой доступа)."""

    @property
    def binding_keys(self) -> tuple[str, ...]:
        """События ленты."""
        return (FeedAppended.routing_key,)

    def supports(self, envelope: EventEnvelope) -> bool:
        """Событие ленты."""
        return envelope.routing_key == FeedAppended.routing_key

    def resolve(self, envelope: EventEnvelope) -> tuple[str, dict[str, Any]]:
        """Топик и номер события."""
        return FeedTopic.of(str(envelope.payload["conversation_id"])), {"seq": int(envelope.payload["seq"])}
