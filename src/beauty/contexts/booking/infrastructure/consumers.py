"""Консьюмеры Booking: имена клиентов из картотеки мастера."""

from __future__ import annotations

from uuid import UUID

from beauty.contexts.booking.application.commands import RenameBookingClient
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

CLIENTS_RENAMED = "clientbook.client.renamed"


class ClientRenamedConsumer(IntegrationEventHandler):
    """Мастер дал клиенту имя → подпись в открытых заявках и записях (график мастера)."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Перевести событие Clientbook в команду своего контекста."""
        payload = envelope.payload
        name = payload.get("name")
        await self._mediator.send(
            RenameBookingClient(
                master_id=UUID(str(payload["master_id"])),
                client_id=UUID(str(payload["client_id"])),
                name=None if name is None else str(name),
            )
        )
