"""Агрегат ``Broadcast`` — рассылка объявления мастера всем его клиентам.

Черновик правится сколько угодно (текст, фото); отправка — необратима и не чаще раза в
сутки. Доставка идёт порциями в фоне: курсор (последняя обработанная переписка) и счётчик
доставленных живут в агрегате, поэтому повтор порции не шлёт объявление второй раз.
Получатели — переписки, открытые до начала отправки.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from beauty.contexts.conversations.domain.errors import (
    BroadcastCooldown,
    BroadcastNotDraft,
    BroadcastsBlocked,
    InvalidBroadcast,
    NoRecipients,
)
from beauty.contexts.conversations.domain.events import BroadcastFinished, BroadcastStarted
from beauty.shared.domain.aggregate import AggregateRoot

MAX_BROADCAST_TEXT = 1000
COOLDOWN = timedelta(hours=24)


class BroadcastStatus(StrEnum):
    """Состояние рассылки."""

    DRAFT = "draft"
    SENDING = "sending"
    SENT = "sent"


class BroadcastOrigin(StrEnum):
    """Кто подготовил черновик."""

    MASTER = "master"
    AGENT = "agent"


def broadcast_text(text: str) -> str:
    """Обрезанный текст в пределах лимита."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_BROADCAST_TEXT:
        raise InvalidBroadcast()
    return cleaned


def next_allowed(last_started_at: datetime | None, now: datetime) -> datetime | None:
    """Когда можно следующую рассылку (``None`` — уже можно)."""
    if last_started_at is None:
        return None
    ready = last_started_at + COOLDOWN
    return ready if ready > now else None


class Broadcast(AggregateRoot):
    """Рассылка мастера."""

    def __init__(
        self, broadcast_id: UUID, master_id: UUID, text: str, origin: BroadcastOrigin, created_at: datetime
    ) -> None:
        """Создать черновик (используйте ``draft``)."""
        self.id = broadcast_id
        self.master_id = master_id
        self.text = broadcast_text(text)
        self.photo_key: str | None = None
        self.status = BroadcastStatus.DRAFT
        self.origin = origin
        self.recipients = 0
        self.delivered = 0
        self.cursor: UUID | None = None
        self.created_at = created_at
        self.updated_at = created_at
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None

    @classmethod
    def draft(
        cls, *, broadcast_id: UUID, master_id: UUID, text: str, origin: BroadcastOrigin, now: datetime
    ) -> Broadcast:
        """Новый черновик."""
        return cls(broadcast_id, master_id, text, origin, now)

    def edit(self, text: str, now: datetime) -> None:
        """Новый текст черновика."""
        self._ensure_draft()
        self.text = broadcast_text(text)
        self.updated_at = now

    def set_photo(self, key: str | None, now: datetime) -> str | None:
        """Фото черновика (``None`` — убрать); вернуть ключ прежнего фото."""
        self._ensure_draft()
        previous, self.photo_key = self.photo_key, key
        self.updated_at = now
        return previous

    def ensure_discardable(self) -> None:
        """Удалить можно только черновик."""
        self._ensure_draft()

    def start(
        self, *, recipients: int, last_started_at: datetime | None, blocked: bool, now: datetime
    ) -> None:
        """Отправить: проверки запрета, лимита и получателей; доставка — по событию."""
        self._ensure_draft()
        if blocked:
            raise BroadcastsBlocked()
        ready = next_allowed(last_started_at, now)
        if ready is not None:
            raise BroadcastCooldown(
                f"Не чаще одной рассылки в сутки — следующая после {ready:%d.%m %H:%M} UTC"
            )
        if recipients <= 0:
            raise NoRecipients()
        self.status = BroadcastStatus.SENDING
        self.recipients = recipients
        self.started_at = now
        self.updated_at = now
        self._record(
            BroadcastStarted(
                occurred_at=now, broadcast_id=self.id, master_id=self.master_id, recipients=recipients
            )
        )

    def advance(self, cursor: UUID, delivered: int, now: datetime) -> None:
        """Порция доставлена: курсор — последняя обработанная переписка."""
        if self.status is not BroadcastStatus.SENDING:
            return
        self.cursor = cursor
        self.delivered += delivered
        self.updated_at = now

    def finish(self, now: datetime) -> None:
        """Получатели закончились."""
        if self.status is not BroadcastStatus.SENDING:
            return
        self.status = BroadcastStatus.SENT
        self.finished_at = now
        self.updated_at = now
        self._record(
            BroadcastFinished(
                occurred_at=now, broadcast_id=self.id, master_id=self.master_id, delivered=self.delivered
            )
        )

    def _ensure_draft(self) -> None:
        if self.status is not BroadcastStatus.DRAFT:
            raise BroadcastNotDraft()
