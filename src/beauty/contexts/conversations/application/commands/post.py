"""Сообщение клиента: текст, голосовое или намерение записаться."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.conversations.application.commands.base import load_conversation, post, revise
from beauty.contexts.conversations.application.dto import MessageView
from beauty.contexts.conversations.application.errors import (
    MasterNotFoundError,
    OfferNotFoundError,
    ServiceNotFoundError,
)
from beauty.contexts.conversations.application.ports import MasterCatalog
from beauty.contexts.conversations.application.uow import ConversationsUnitOfWork
from beauty.contexts.conversations.domain.content import MessageContent, TextContent, VoiceContent
from beauty.contexts.conversations.domain.conversation import Conversation, NeedsMaster
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.application.cqrs import Command, Handler
from beauty.shared.application.phrases import day_label, time_label
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator

QUESTION_INTENTS = frozenset({"text", "voice"})
"""Свободный текст и голосовые: без агента ответить на них может только мастер."""


@dataclass(frozen=True, slots=True)
class TextBody:
    """Свободный текст."""

    text: str


@dataclass(frozen=True, slots=True)
class VoiceBody:
    """Голосовое, уже сохранённое в хранилище."""

    audio_key: str
    duration: float


@dataclass(frozen=True, slots=True)
class RequestSlotsBody:
    """«Хочу записаться — какое время свободно?» (текст показывается в ленте)."""

    text: str
    service_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class BookSlotBody:
    """Запрос конкретного окна, выбранного на странице мастера."""

    service_id: UUID
    start: datetime


@dataclass(frozen=True, slots=True)
class SlotPickBody:
    """Выбор окна из предложения администратора."""

    offer_id: UUID
    start: datetime


type ClientBody = TextBody | VoiceBody | RequestSlotsBody | BookSlotBody | SlotPickBody


@dataclass(frozen=True, slots=True)
class PostClientMessage(Command[MessageView]):
    """Клиент пишет в свою переписку; ``client_message_id`` — ключ идемпотентности."""

    conversation_id: UUID
    client_id: UUID
    client_message_id: UUID
    body: ClientBody


@dataclass(frozen=True, slots=True)
class _Draft:
    """Содержимое и намерение сообщения клиента."""

    content: MessageContent
    intent: str
    service_id: UUID | None = None
    start: datetime | None = None
    offer_id: UUID | None = None


class PostClientMessageHandler(Handler[PostClientMessage, MessageView]):
    """Сохраняет сообщение; ответ администратора — асинхронно, по событию."""

    def __init__(
        self, uow: ConversationsUnitOfWork, catalog: MasterCatalog, clock: Clock, ids: IdGenerator
    ) -> None:
        """Получить зависимости."""
        self._uow = uow
        self._catalog = catalog
        self._clock = clock
        self._ids = ids

    async def handle(self, message: PostClientMessage) -> MessageView:
        """Принять сообщение (повтор с тем же ``client_message_id`` вернёт исходное)."""
        async with self._uow as uow:
            conversation = await load_conversation(uow, message.conversation_id, message.client_id)
            existing = await uow.messages.by_client_id(conversation.id, message.client_message_id)
            if existing is not None:
                return MessageView.of(existing)
            now = self._clock.now()
            draft = await self._draft(uow, conversation, message.body, now)
            posted = Message.from_client(
                message_id=self._ids.new(),
                conversation_id=conversation.id,
                master_id=conversation.master_id,
                client_id=conversation.client_id,
                client_message_id=message.client_message_id,
                content=draft.content,
                intent=draft.intent,
                now=now,
                text=draft.content.text if isinstance(draft.content, TextContent) else None,
                service_id=draft.service_id,
                start=draft.start,
                offer_id=draft.offer_id,
            )
            post(uow, conversation, posted, now)
            if draft.intent in QUESTION_INTENTS:
                conversation.ask_master(NeedsMaster.QUESTION, now)
            await uow.commit()
        return MessageView.of(posted)

    async def _draft(
        self, uow: ConversationsUnitOfWork, conversation: Conversation, body: ClientBody, now: datetime
    ) -> _Draft:
        match body:
            case TextBody(text):
                return _Draft(TextContent(text), "text")
            case VoiceBody(audio_key, duration):
                return _Draft(VoiceContent(audio_key, duration), "voice")
            case RequestSlotsBody(text, service_id):
                return _Draft(TextContent(text), "request_slots", service_id=service_id)
            case BookSlotBody(service_id, start):
                master = await self._catalog.by_id(conversation.master_id)
                if master is None:
                    raise MasterNotFoundError()
                service = master.service(service_id)
                if service is None:
                    raise ServiceNotFoundError()
                local = start.astimezone(ZoneInfo(master.timezone))
                when = f"{day_label(local.date())} в {time_label(local)}"
                text = f"Хочу записаться: {service.title.lower()}, {when}"
                return _Draft(TextContent(text), "book_slot", service_id=service.id, start=start)
            case SlotPickBody(offer_id, start):
                offer = await uow.messages.get(offer_id)
                if offer is None or offer.conversation_id != conversation.id:
                    raise OfferNotFoundError()
                picked = offer.select_slot(start, now).find(start)
                assert picked is not None  # select_slot уже проверил окно
                revise(conversation, offer, now)
                return _Draft(
                    TextContent(time_label(picked.start)),
                    "slot_pick",
                    service_id=picked.service_id,
                    start=picked.start,
                    offer_id=offer.id,
                )
