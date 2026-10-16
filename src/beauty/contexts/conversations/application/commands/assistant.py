"""Администратор записи: отвечает на намерения клиента записаться.

Сейчас это детерминированный обработчик намерений (``book_slot``, ``slot_pick``,
``request_slots``); ИИ-агент следующей итерации встанет на то же событие
``ClientMessagePosted`` и возьмёт на себя свободный текст и голосовые.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.conversations.application.commands.base import load_conversation, post
from beauty.contexts.conversations.application.errors import SlotNotAvailableError
from beauty.contexts.conversations.application.phrases import capitalize, day_phrase
from beauty.contexts.conversations.application.ports import (
    BookingDesk,
    MasterCatalog,
    MasterInfo,
    ServiceInfo,
)
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.content import (
    BookingCardContent,
    MessageContent,
    SlotOfferContent,
    TextContent,
)
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

SEARCH_LIMIT = 40
OFFER_SIZE = 6
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

    async def handle(self, message: AssistClient) -> None:
        """Ответить, если намерение понятно без агента."""
        if message.intent in BOOKING_INTENTS and message.service_id and message.start:
            reply = await self._book(message, message.service_id, message.start)
        elif message.intent == "request_slots":
            reply = await self._offer(message.master_id, message.service_id, None, prefix=None)
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
            await uow.commit()

    async def _book(self, message: AssistClient, service_id: UUID, start: datetime) -> MessageContent | None:
        try:
            requested = await self._booking.request(message.master_id, message.client_id, service_id, start)
        except SlotNotAvailableError:
            return await self._offer(message.master_id, service_id, start, prefix="Это время уже заняли.")
        return BookingCardContent(requested.appointment_id, requested.revision, dict(requested.appointment))

    async def _offer(
        self, master_id: UUID, service_id: UUID | None, around: datetime | None, prefix: str | None
    ) -> MessageContent | None:
        master = await self._catalog.by_id(master_id)
        service = None if master is None else master.service(service_id)
        if master is None or service is None:
            return None
        zone = ZoneInfo(master.timezone)
        window_from = None if around is None else _day_start(around.astimezone(zone).date(), zone)
        slots = await self._catalog.free_slots(master.id, service.id, window_from, SEARCH_LIMIT)
        if not slots:
            return TextContent(
                f"{prefix + ' ' if prefix else ''}Свободных окон в ближайшие дни нет — "
                f"{master.name} ответит здесь и предложит время."
            )
        first_day = slots[0].start.astimezone(zone).date()
        same_day = tuple(s for s in slots if s.start.astimezone(zone).date() == first_day)[:OFFER_SIZE]
        today = self._clock.now().astimezone(zone).date()
        return SlotOfferContent(_offer_text(master, service, first_day, today, prefix), same_day)


def _offer_text(master: MasterInfo, service: ServiceInfo, day: date, today: date, prefix: str | None) -> str:
    when = capitalize(day_phrase(day, today))
    if prefix:
        return f"{prefix} {when} свободно:"
    return f"{when} на «{service.title.lower()}» ({service.duration_min} мин) свободно:"


def _day_start(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(), tzinfo=zone)
