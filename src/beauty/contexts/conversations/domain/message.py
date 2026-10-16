"""Агрегат ``Message`` — сообщение ленты переписки."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.domain.content import (
    Author,
    BookingCardContent,
    MessageContent,
    SlotOfferContent,
    kind_of,
)
from beauty.contexts.conversations.domain.errors import NotAnOffer, OfferAlreadyUsed, SlotNotOffered
from beauty.contexts.conversations.domain.events import ClientMessagePosted
from beauty.shared.domain.aggregate import AggregateRoot


class Message(AggregateRoot):
    """Сообщение клиента, администратора или мастера."""

    def __init__(
        self,
        message_id: UUID,
        conversation_id: UUID,
        author: Author,
        content: MessageContent,
        client_message_id: UUID | None,
        ai_generated: bool,
        created_at: datetime,
    ) -> None:
        """Создать сообщение (используйте фабрики)."""
        self.id = message_id
        self.conversation_id = conversation_id
        self.author = author
        self.content = content
        self.kind = kind_of(content)
        self.client_message_id = client_message_id
        self.ai_generated = ai_generated
        self.appointment_id = content.appointment_id if isinstance(content, BookingCardContent) else None
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def from_client(
        cls,
        *,
        message_id: UUID,
        conversation_id: UUID,
        master_id: UUID,
        client_id: UUID,
        client_message_id: UUID,
        content: MessageContent,
        intent: str,
        now: datetime,
        text: str | None = None,
        service_id: UUID | None = None,
        start: datetime | None = None,
        offer_id: UUID | None = None,
    ) -> Message:
        """Сообщение клиента; администратор узнаёт о нём по событию."""
        message = cls(message_id, conversation_id, Author.CLIENT, content, client_message_id, False, now)
        message._record(
            ClientMessagePosted(
                occurred_at=now,
                conversation_id=conversation_id,
                message_id=message_id,
                master_id=master_id,
                client_id=client_id,
                intent=intent,
                text=text,
                service_id=service_id,
                start=start,
                offer_id=offer_id,
            )
        )
        return message

    @classmethod
    def from_agent(
        cls,
        *,
        message_id: UUID,
        conversation_id: UUID,
        content: MessageContent,
        now: datetime,
        ai_generated: bool = False,
    ) -> Message:
        """Сообщение администратора: детерминированное (запись) или ответ ИИ-агента."""
        return cls(message_id, conversation_id, Author.AGENT, content, None, ai_generated, now)

    def select_slot(self, start: datetime, now: datetime) -> SlotOfferContent:
        """Отметить выбранное окно в предложении; вернуть обновлённое предложение."""
        offer = self.content
        if not isinstance(offer, SlotOfferContent):
            raise NotAnOffer()
        slot = offer.find(start)
        if slot is None:
            raise SlotNotOffered()
        if offer.selected_start is not None:
            raise OfferAlreadyUsed()
        self.content = replace(offer, selected_start=slot.start)
        self.updated_at = now
        return self.content

    def refresh_appointment(self, revision: int, appointment: Mapping[str, Any], now: datetime) -> bool:
        """Обновить снимок записи в карточке; более старая ревизия игнорируется."""
        card = self.content
        if not isinstance(card, BookingCardContent) or revision <= card.revision:
            return False
        self.content = BookingCardContent(card.appointment_id, revision, dict(appointment))
        self.updated_at = now
        return True
