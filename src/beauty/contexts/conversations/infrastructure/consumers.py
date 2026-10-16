"""Консьюмеры Conversations: сообщения клиентов и изменения записей."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.application.commands import AssistClient, SyncAppointment
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

CLIENT_MESSAGES = "conversations.client.message_posted"
APPOINTMENTS = "booking.appointment.*"


def _uuid(value: Any) -> UUID | None:
    return None if value is None else UUID(str(value))


class ClientMessageConsumer(IntegrationEventHandler):
    """Клиент написал → администратор записи отвечает."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Перевести событие в команду."""
        payload = envelope.payload
        start = payload.get("start")
        await self._mediator.send(
            AssistClient(
                conversation_id=UUID(str(payload["conversation_id"])),
                master_id=UUID(str(payload["master_id"])),
                client_id=UUID(str(payload["client_id"])),
                intent=str(payload["intent"]),
                service_id=_uuid(payload.get("service_id")),
                start=None if start is None else datetime.fromisoformat(str(start)),
            )
        )


class AppointmentConsumer(IntegrationEventHandler):
    """Запись изменилась → карточка и системное сообщение в переписке."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Перевести событие Booking в команду своего контекста."""
        payload = envelope.payload
        appointment = dict(payload["appointment"])
        await self._mediator.send(
            SyncAppointment(
                master_id=UUID(str(payload["master_id"])),
                client_id=UUID(str(payload["client_id"])),
                appointment_id=UUID(str(payload["appointment_id"])),
                revision=int(payload["revision"]),
                appointment=appointment,
                status=str(appointment["status"]),
                reason=payload.get("reason"),
                reschedule_of=_uuid(payload.get("reschedule_of")),
                offer_alternatives=bool(payload.get("offer_alternatives", False)),
                event=envelope.routing_key.rsplit(".", 1)[-1],
            )
        )
