"""Консьюмеры Conversations: сообщения клиентов, голосовые на расшифровку, изменения записей,
имена клиентов из картотеки мастера."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.application.commands import (
    AssistClient,
    DeliverBroadcast,
    RenameConversationClient,
    SyncAppointment,
    TranscribeVoice,
)
from beauty.shared.application.mediator import Mediator
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

CLIENT_MESSAGES = "conversations.client.message_posted"
APPOINTMENTS = "booking.appointment.*"
MESSAGES_ADDED = "conversations.message.added"
CLIENTS_RENAMED = "clientbook.client.renamed"
BROADCASTS_STARTED = "conversations.broadcast.started"


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


class VoiceConsumer(IntegrationEventHandler):
    """Новое голосовое → расшифровка."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Только голосовые."""
        if envelope.payload.get("kind") == "voice":
            await self._mediator.send(TranscribeVoice(UUID(str(envelope.payload["message_id"]))))


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


class ClientRenamedConsumer(IntegrationEventHandler):
    """Мастер дал клиенту имя → подпись клиента в переписке."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Перевести событие Clientbook в команду своего контекста."""
        payload = envelope.payload
        name = payload.get("name")
        await self._mediator.send(
            RenameConversationClient(
                master_id=UUID(str(payload["master_id"])),
                client_id=UUID(str(payload["client_id"])),
                name=None if name is None else str(name),
            )
        )


class BroadcastConsumer(IntegrationEventHandler):
    """Мастер отправил рассылку → объявление каждому клиенту (порциями)."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    async def handle(self, envelope: EventEnvelope) -> None:
        """Доставить."""
        await self._mediator.send(DeliverBroadcast(UUID(str(envelope.payload["broadcast_id"]))))
