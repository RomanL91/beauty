"""Домен Conversations: сообщения, лента, тексты, сериализация содержимого."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

import pytest

from beauty.contexts.conversations.application.phrases import capitalize, day_label, day_phrase
from beauty.contexts.conversations.domain.content import (
    BookingCardContent,
    MessageContent,
    OfferedSlot,
    SlotOfferContent,
    SystemContent,
    TextContent,
    Tone,
    VoiceContent,
)
from beauty.contexts.conversations.domain.conversation import Conversation, FeedChange
from beauty.contexts.conversations.domain.errors import (
    InvalidMessage,
    NotAnOffer,
    OfferAlreadyUsed,
    SlotNotOffered,
)
from beauty.contexts.conversations.domain.events import ClientMessagePosted, FeedAppended
from beauty.contexts.conversations.domain.message import Message
from beauty.contexts.conversations.infrastructure.serialization import dump_content, load_content

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
ALMATY = timezone(timedelta(hours=5))
TEN = datetime(2026, 10, 16, 10, 0, tzinfo=ALMATY)
CONVERSATION = UUID(int=1)


def offer() -> Message:
    """Предложение двух окон."""
    slots = tuple(
        OfferedSlot(TEN + timedelta(hours=h), TEN + timedelta(hours=h, minutes=40), UUID(int=9))
        for h in (0, 1)
    )
    return Message.from_agent(
        message_id=UUID(int=2),
        conversation_id=CONVERSATION,
        content=SlotOfferContent("Завтра свободно:", slots),
        now=NOW,
    )


def test_content_validation() -> None:
    assert TextContent("  привет ").text == "привет"
    with pytest.raises(InvalidMessage):
        TextContent("   ")
    with pytest.raises(InvalidMessage):
        VoiceContent("voice/2026/10/x.webm", 121)
    with pytest.raises(InvalidMessage):
        SlotOfferContent("пусто", ())


def test_select_slot_once_by_absolute_time() -> None:
    message = offer()
    with pytest.raises(SlotNotOffered):
        message.select_slot(TEN + timedelta(minutes=30), NOW)
    updated = message.select_slot(TEN.astimezone(UTC), NOW)  # то же время в другом поясе
    assert updated.selected_start == TEN
    with pytest.raises(OfferAlreadyUsed):
        message.select_slot(TEN + timedelta(hours=1), NOW)
    text = Message.from_agent(
        message_id=UUID(int=3), conversation_id=CONVERSATION, content=TextContent("а"), now=NOW
    )
    with pytest.raises(NotAnOffer):
        text.select_slot(TEN, NOW)


def test_card_refresh_ignores_stale_revisions() -> None:
    card = Message.from_agent(
        message_id=UUID(int=4),
        conversation_id=CONVERSATION,
        content=BookingCardContent(UUID(int=5), 2, {"status": "confirmed"}),
        now=NOW,
    )
    assert card.appointment_id == UUID(int=5)
    assert not card.refresh_appointment(1, {"status": "requested"}, NOW)
    assert card.refresh_appointment(3, {"status": "cancelled"}, NOW)
    assert card.content == BookingCardContent(UUID(int=5), 3, {"status": "cancelled"})


def test_feed_numbers_events_and_client_intent_event() -> None:
    conversation = Conversation.open(
        conversation_id=CONVERSATION, master_id=UUID(int=7), client_id=UUID(int=8), now=NOW
    )
    message = Message.from_client(
        message_id=UUID(int=6),
        conversation_id=CONVERSATION,
        master_id=UUID(int=7),
        client_id=UUID(int=8),
        client_message_id=UUID(int=10),
        content=TextContent("Хочу записаться"),
        intent="book_slot",
        now=NOW,
        service_id=UUID(int=9),
        start=TEN,
    )
    assert conversation.record(message, FeedChange.CREATED, NOW) == 1
    assert conversation.record(message, FeedChange.UPDATED, NOW) == 2
    created, updated = conversation.pull_events()
    assert isinstance(created, FeedAppended)
    assert (created.seq, created.change, updated.change) == (1, "message.created", "message.updated")
    (intent,) = message.pull_events()
    assert isinstance(intent, ClientMessagePosted)
    assert (intent.intent, intent.start) == ("book_slot", TEN)
    foreign = offer()
    foreign.conversation_id = UUID(int=99)
    with pytest.raises(ValueError, match="другой переписки"):
        conversation.record(foreign, FeedChange.CREATED, NOW)


@pytest.mark.parametrize(
    "content",
    [
        TextContent("Здравствуйте"),
        VoiceContent("voice/2026/10/0192a0c0-0000-7000-8000-000000000001.webm", 3.4),
        offer().content,
        BookingCardContent(UUID(int=5), 1, {"id": "x", "status": "requested"}),
        SystemContent("Запись подтверждена", Tone.SUCCESS),
    ],
)
def test_content_json_roundtrip(content: MessageContent) -> None:
    assert load_content(dump_content(content)) == content


def test_russian_dates() -> None:
    today = date(2026, 10, 15)
    assert day_label(date(2026, 10, 17)) == "сб, 17 октября"
    assert day_phrase(today, today) == "сегодня"
    assert day_phrase(date(2026, 10, 16), today) == "завтра"
    assert capitalize(day_phrase(date(2026, 10, 19), today)) == "В пн, 19 октября"
