"""Realtime-топики Conversations: «в ленте новое событие»."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from beauty.contexts.conversations.domain.events import ConversationChanged, FeedAppended
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


class MasterTopic:
    """Топик кабинета мастера."""

    PREFIX = "conversations.master"

    @classmethod
    def of(cls, master_id: UUID | str) -> str:
        """Топик мастера."""
        return f"{cls.PREFIX}:{master_id}"


class MasterTopicResolver(TopicResolver):
    """События кабинета: сообщения и сводки переписок мастера, его записи.

    Сообщение и сводку поток кабинета перечитывает сам (с проверкой владельца),
    снимок записи берётся из события Booking как есть.
    """

    _APPOINTMENTS = "booking.appointment."

    @property
    def binding_keys(self) -> tuple[str, ...]:
        """События ленты, сводок и записей."""
        return (FeedAppended.routing_key, ConversationChanged.routing_key, "booking.appointment.*")

    def supports(self, envelope: EventEnvelope) -> bool:
        """Событие для кабинета."""
        key = envelope.routing_key
        return key in (FeedAppended.routing_key, ConversationChanged.routing_key) or key.startswith(
            self._APPOINTMENTS
        )

    def resolve(self, envelope: EventEnvelope) -> tuple[str, dict[str, Any]]:
        """Топик мастера и что произошло."""
        payload = envelope.payload
        topic = MasterTopic.of(str(payload["master_id"]))
        if envelope.routing_key == FeedAppended.routing_key:
            return topic, {
                "kind": "message",
                "change": payload["change"],
                "conversation_id": str(payload["conversation_id"]),
                "message_id": str(payload["message_id"]),
            }
        if envelope.routing_key == ConversationChanged.routing_key:
            return topic, {"kind": "conversation", "conversation_id": str(payload["conversation_id"])}
        return topic, {"kind": "appointment", "appointment": payload["appointment"]}
