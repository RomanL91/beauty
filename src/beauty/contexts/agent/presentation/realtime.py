"""Realtime: лента поручений → поток кабинета мастера (``/me/events``, ``conversation_id = null``)."""

from __future__ import annotations

from typing import Any

from beauty.contexts.agent.domain.events import OfficeFeedChanged
from beauty.contexts.agent.presentation.api.render import OfficeRenderer
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.realtime.bridge import TopicResolver
from beauty.shared.infrastructure.realtime.cabinet import FRAME_SIGNAL, MasterTopic


class OfficeFeedResolver(TopicResolver):
    """Сообщение ленты — готовым кадром ``message.created|updated`` в топик кабинета мастера.

    Топик — только этого мастера, а снимок — его собственная лента, поэтому кадр собирается
    сразу (ссылка на голосовое подписывается здесь, при доставке).
    """

    def __init__(self, renderer: OfficeRenderer) -> None:
        """Получить рендерер."""
        self._renderer = renderer

    @property
    def binding_keys(self) -> tuple[str, ...]:
        """События ленты поручений."""
        return (OfficeFeedChanged.routing_key,)

    def supports(self, envelope: EventEnvelope) -> bool:
        """Событие ленты поручений."""
        return envelope.routing_key == OfficeFeedChanged.routing_key

    def resolve(self, envelope: EventEnvelope) -> tuple[str, dict[str, Any]]:
        """Топик мастера и готовый кадр."""
        payload = envelope.payload
        change = str(payload["change"])
        return MasterTopic.of(str(payload["master_id"])), {
            "kind": FRAME_SIGNAL,
            "event": change,
            "data": {
                "type": change,
                "conversation_id": None,
                "message": self._renderer.render(payload["message"]),
            },
        }
