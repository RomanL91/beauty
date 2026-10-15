"""Realtime-топики Identity: статус входа для SSE браузера."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from beauty.contexts.identity.domain.events import AuthChallengeCompleted, AuthChallengeRejected
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.realtime.bridge import TopicResolver


class ChallengeTopic:
    """Имя топика для конкретного входа."""

    PREFIX = "identity.auth_challenge"

    @classmethod
    def for_challenge(cls, challenge_id: UUID | str) -> str:
        """Топик входа."""
        return f"{cls.PREFIX}:{challenge_id}"


class AuthChallengeTopicResolver(TopicResolver):
    """Переводит события входа в сообщения для браузера.

    Наружу уходит только новый статус — без id учётной записи и прочих данных.
    """

    _STATUS_BY_KEY: ClassVar[dict[str, str]] = {
        AuthChallengeCompleted.routing_key: "completed",
        AuthChallengeRejected.routing_key: "rejected",
    }

    @property
    def binding_keys(self) -> tuple[str, ...]:
        """События входа."""
        return tuple(self._STATUS_BY_KEY)

    def supports(self, envelope: EventEnvelope) -> bool:
        """Событие завершения или отклонения входа."""
        return envelope.routing_key in self._STATUS_BY_KEY

    def resolve(self, envelope: EventEnvelope) -> tuple[str, dict[str, Any]]:
        """Топик входа и его новый статус."""
        challenge_id = str(envelope.payload["challenge_id"])
        return ChallengeTopic.for_challenge(challenge_id), {
            "status": self._STATUS_BY_KEY[envelope.routing_key]
        }
