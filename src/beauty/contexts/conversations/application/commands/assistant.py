"""Администратор записи: отвечает на намерения клиента записаться.

Сейчас это детерминированный обработчик намерений (``book_slot``, ``slot_pick``,
``request_slots``); ИИ-агент следующей итерации встанет на то же событие
``ClientMessagePosted`` и возьмёт на себя свободный текст и голосовые.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.contexts.conversations.application.commands.base import load_conversation, post
from beauty.contexts.conversations.application.errors import SlotNotAvailableError
from beauty.contexts.conversations.application.offers import SlotOfferComposer
from beauty.contexts.conversations.application.ports import BookingDesk, MasterCatalog
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.content import BookingCardContent, MessageContent
from beauty.contexts.conversations.domain.conversation import NeedsMaster
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

BOOKING_INTENTS = frozenset({"book_slot", "slot_pick"})


@dataclass(frozen=True, slots=True)
class AssistClient(Command[None]):
    """Ответить на сообщение клиента (из события ``ClientMessagePosted``)."""

    conversation_id: UUID
    master_id: UUID
    client_id: UUID
    intent: str
    service_id: UUID | None = None
    start: datetime | None = None


class AssistClientHandler(Handler[AssistClient, None]):
    """Заявка → карточка; занято → другие окна; «какое время свободно?» → окна."""

    def __init__(
        self,
        uow: ConversationsUnitOfWork,
        catalog: MasterCatalog,
        booking: BookingDesk,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._catalog = catalog
        self._booking = booking
        self._clock = clock
        self._ids = ids
        self._offers = SlotOfferComposer(catalog, clock)

    async def handle(self, message: AssistClient) -> None:
        """Ответить, если намерение понятно без агента."""
        if message.intent in BOOKING_INTENTS and message.service_id and message.start:
            reply = await self._book(message, message.service_id, message.start)
        elif message.intent == "request_slots":
            reply = await self._offers.compose(message.master_id, message.service_id)
        else:
            return
        if reply is None:
            return
        async with self._uow as uow:
            conversation = await load_conversation(uow, message.conversation_id)
            now = self._clock.now()
            answer = Message.from_agent(
                message_id=self._ids.new(), conversation_id=conversation.id, content=reply, now=now
            )
            post(uow, conversation, answer, now)
            if isinstance(reply, BookingCardContent):
                # Событие Booking о той же заявке придёт с той же ревизией и ничего не изменит.
                conversation.ask_master(NeedsMaster.REQUEST, now)
            await uow.commit()

    async def _book(self, message: AssistClient, service_id: UUID, start: datetime) -> MessageContent | None:
        try:
            requested = await self._booking.request(message.master_id, message.client_id, service_id, start)
        except SlotNotAvailableError:
            return await self._offers.compose(
                message.master_id, service_id, around=start, prefix="Это время уже заняли."
            )
        return BookingCardContent(requested.appointment_id, requested.revision, dict(requested.appointment))
