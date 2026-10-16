"""Карточки заявок: переписка следит за записями из Booking."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.application.commands.base import post, revise
from beauty.contexts.conversations.application.phrases import day_label, time_label
from beauty.contexts.conversations.application.ports import MasterCatalog
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.content import BookingCardContent, SystemContent, Tone
from beauty.contexts.conversations.domain.conversation import Conversation
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class SyncAppointment(Command[None]):
    """Запись изменилась (событие Booking): обновить карточку и сообщить клиенту.

    ``status`` — новый статус, ``reason`` — причина отмены (``declined``, ``expired``,
    ``client_cancelled``, ``rescheduled``).
    """

    master_id: UUID
    client_id: UUID
    appointment_id: UUID
    revision: int
    appointment: Mapping[str, Any]
    status: str
    reason: str | None = None
    reschedule_of: UUID | None = None


class SyncAppointmentHandler(Handler[SyncAppointment, None]):
    """Карточка обновляется только более новой ревизией — порядок доставки не важен."""

    def __init__(
        self, uow: ConversationsUnitOfWork, catalog: MasterCatalog, clock: Clock, ids: IdGenerator
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._catalog = catalog
        self._clock = clock
        self._ids = ids

    async def handle(self, message: SyncAppointment) -> None:
        """Обновить или создать карточку и добавить системное сообщение."""
        async with self._uow as uow:
            conversation = await uow.conversations.find(message.master_id, message.client_id)
            if conversation is None:
                return
            now = self._clock.now()
            card = await uow.messages.card_of(conversation.id, message.appointment_id)
            if card is None:
                self._post(
                    uow,
                    conversation,
                    BookingCardContent(message.appointment_id, message.revision, dict(message.appointment)),
                    now,
                )
            elif card.refresh_appointment(message.revision, message.appointment, now):
                revise(conversation, card, now)
            else:
                return
            note = await self._note(message)
            if note is not None:
                self._post(uow, conversation, note, now)
            await uow.commit()

    def _post(
        self,
        uow: ConversationsUnitOfWork,
        conversation: Conversation,
        content: BookingCardContent | SystemContent,
        now: datetime,
    ) -> None:
        reply = Message.from_agent(
            message_id=self._ids.new(), conversation_id=conversation.id, content=content, now=now
        )
        post(uow, conversation, reply, now)

    async def _note(self, message: SyncAppointment) -> SystemContent | None:
        if message.status == "confirmed":
            start = datetime.fromisoformat(str(message.appointment["start"]))
            return SystemContent(
                f"Запись подтверждена: {day_label(start.date())} в {time_label(start)}. Ждём вас!",
                Tone.SUCCESS,
            )
        if message.status != "cancelled":
            return None
        if message.reason == "declined":
            master = await self._catalog.by_id(message.master_id)
            who = master.name if master is not None else "Мастер"
            return SystemContent(f"{who} не сможет принять в это время — выберите другое окно.", Tone.WARNING)
        if message.reason == "expired":
            return SystemContent(
                "Заявка не подтверждена вовремя, окно освободилось — выберите другое время.", Tone.WARNING
            )
        if message.reason == "client_cancelled" and message.reschedule_of is None:
            return SystemContent("Запись отменена, окно освободилось.", Tone.INFO)
        return None
