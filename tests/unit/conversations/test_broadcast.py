"""Рассылка: черновик, отправка с проверками, доставка порциями."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from beauty.contexts.conversations.domain.broadcast import (
    Broadcast,
    BroadcastOrigin,
    BroadcastStatus,
    next_allowed,
)
from beauty.contexts.conversations.domain.errors import (
    BroadcastCooldown,
    BroadcastNotDraft,
    BroadcastsBlocked,
    InvalidBroadcast,
    NoRecipients,
)
from beauty.contexts.conversations.domain.events import BroadcastFinished, BroadcastStarted
from tests.fakes import FrozenClock


def draft(clock: FrozenClock) -> Broadcast:
    return Broadcast.draft(
        broadcast_id=uuid4(),
        master_id=uuid4(),
        text=" Скидка 20% ",
        origin=BroadcastOrigin.MASTER,
        now=clock.now(),
    )


def test_draft_edit_photo_and_checks_before_sending(clock: FrozenClock) -> None:
    broadcast = draft(clock)
    assert (broadcast.text, broadcast.status) == ("Скидка 20%", BroadcastStatus.DRAFT)
    broadcast.edit("С 1 ноября — массаж лица", clock.now())
    assert broadcast.set_photo("announcements/a.jpg", clock.now()) is None
    assert broadcast.set_photo("announcements/b.jpg", clock.now()) == "announcements/a.jpg"
    with pytest.raises(InvalidBroadcast):
        broadcast.edit("x" * 1001, clock.now())
    with pytest.raises(BroadcastsBlocked):
        broadcast.start(recipients=3, last_started_at=None, blocked=True, now=clock.now())
    with pytest.raises(BroadcastCooldown):
        broadcast.start(
            recipients=3, last_started_at=clock.now() - timedelta(hours=23), blocked=False, now=clock.now()
        )
    with pytest.raises(NoRecipients):
        broadcast.start(recipients=0, last_started_at=None, blocked=False, now=clock.now())
    assert broadcast.status is BroadcastStatus.DRAFT
    assert broadcast.pull_events() == []


def test_start_advance_finish(clock: FrozenClock) -> None:
    broadcast = draft(clock)
    yesterday = clock.now() - timedelta(hours=24, minutes=1)
    broadcast.start(recipients=3, last_started_at=yesterday, blocked=False, now=clock.now())
    (started,) = broadcast.pull_events()
    assert isinstance(started, BroadcastStarted)
    assert (started.recipients, broadcast.started_at) == (3, clock.now())
    with pytest.raises(BroadcastNotDraft):
        broadcast.edit("Другое", clock.now())
    with pytest.raises(BroadcastNotDraft):
        broadcast.ensure_discardable()
    cursor = uuid4()
    broadcast.advance(cursor, 2, clock.now())
    broadcast.advance(uuid4(), 1, clock.now())
    broadcast.finish(clock.now())
    broadcast.finish(clock.now())  # повтор — без второго события
    events = broadcast.pull_events()
    assert [type(e) for e in events] == [BroadcastFinished]
    assert (broadcast.status, broadcast.delivered) == (BroadcastStatus.SENT, 3)
    broadcast.advance(cursor, 5, clock.now())  # после завершения — не считается
    assert broadcast.delivered == 3


def test_next_allowed(clock: FrozenClock) -> None:
    now = clock.now()
    assert next_allowed(None, now) is None
    assert next_allowed(now - timedelta(hours=25), now) is None
    assert next_allowed(now - timedelta(hours=1), now) == now + timedelta(hours=23)
