"""Агрегат ``Conversation`` — переписка клиента с администратором мастера.

Сообщения — отдельные агрегаты (история неограниченна), а переписка держит то, что
нужно списку чатов мастера и порядку ленты:

* счётчик событий ленты: каждое новое или изменённое сообщение получает номер через
  ``record``; счётчик растёт под блокировкой строки переписки, поэтому номера идут без
  пропусков в порядке коммитов — клиент, продолжающий поток с ``Last-Event-ID``,
  ничего не пропустит;
* сводку для мастера: клиент, кто ведёт диалог, «нужны вы», последнее сообщение,
  непрочитанное, число состоявшихся визитов. Любое изменение сводки — событие
  ``ConversationChanged`` (одно на транзакцию).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from beauty.contexts.conversations.domain.content import (
    Author,
    BookingCardContent,
    MessageContent,
    SlotOfferContent,
    SystemContent,
    TextContent,
    VoiceContent,
)
from beauty.contexts.conversations.domain.events import ConversationChanged, FeedAppended
from beauty.contexts.conversations.domain.message import Message
from beauty.shared.domain.aggregate import AggregateRoot

PREVIEW_LENGTH = 120


class FeedChange(StrEnum):
    """Что произошло с сообщением ленты."""

    CREATED = "message.created"
    UPDATED = "message.updated"


class Handler(StrEnum):
    """Кто отвечает клиенту."""

    AGENT = "agent"
    MASTER = "master"


class NeedsMaster(StrEnum):
    """Почему диалогу нужен мастер."""

    REQUEST = "request"
    QUESTION = "question"


@dataclass(frozen=True, slots=True)
class ClientCard:
    """Клиент глазами мастера."""

    display_name: str
    phone_masked: str


class Conversation(AggregateRoot):
    """Переписка клиента с мастером (одна на пару)."""

    def __init__(
        self,
        conversation_id: UUID,
        master_id: UUID,
        client_id: UUID,
        client: ClientCard,
        created_at: datetime,
    ) -> None:
        """Создать переписку (используйте ``open``)."""
        self.id = conversation_id
        self.master_id = master_id
        self.client_id = client_id
        self.client = client
        self.handler = Handler.AGENT
        self.needs_master: NeedsMaster | None = None
        self.last_message_author: Author | None = None
        self.last_message_preview: str | None = None
        self.last_message_at: datetime | None = None
        self.unread = 0
        self.completed_visits = 0
        self.last_event_seq = 0
        self.created_at = created_at
        self.updated_at = created_at

    @classmethod
    def open(
        cls, *, conversation_id: UUID, master_id: UUID, client_id: UUID, client: ClientCard, now: datetime
    ) -> Conversation:
        """Начать переписку."""
        return cls(conversation_id, master_id, client_id, client, now)

    @property
    def visit_number(self) -> int:
        """Какой визит будет следующим."""
        return self.completed_visits + 1

    # ─────────────────────────── лента ───────────────────────────

    def record(self, message: Message, change: FeedChange, now: datetime) -> int:
        """Зафиксировать событие ленты и вернуть его номер; новое сообщение — в сводку."""
        if message.conversation_id != self.id:
            raise ValueError("Сообщение из другой переписки")
        self.last_event_seq += 1
        self.updated_at = now
        self._record(
            FeedAppended(
                occurred_at=now,
                conversation_id=self.id,
                master_id=self.master_id,
                seq=self.last_event_seq,
                change=change.value,
                message_id=message.id,
            )
        )
        if change is FeedChange.CREATED:
            self.last_message_author = message.author
            self.last_message_preview = preview(message.content)
            self.last_message_at = message.created_at
            if message.author is Author.CLIENT:
                self.unread += 1
            self._changed(now)
        return self.last_event_seq

    # ─────────────────────────── сводка мастера ───────────────────────────

    def ask_master(self, reason: NeedsMaster, now: datetime) -> None:
        """Диалогу нужен мастер (новая заявка; вопрос, на который некому ответить)."""
        if reason is NeedsMaster.QUESTION and self.handler is Handler.MASTER:
            return  # мастер и так ведёт диалог
        if self.needs_master is NeedsMaster.REQUEST and reason is NeedsMaster.QUESTION:
            return  # заявка важнее вопроса
        if self.needs_master is not reason:
            self.needs_master = reason
            self._changed(now)

    def request_resolved(self, now: datetime) -> None:
        """Мастер (или система) решил заявку."""
        if self.needs_master is NeedsMaster.REQUEST:
            self.needs_master = None
            self._changed(now)

    def take_over(self, now: datetime) -> None:
        """Мастер ответил сам: диалог ведёт мастер, всё прочитано."""
        self.set_handler(Handler.MASTER, now)
        if self.needs_master is not None or self.unread:
            self.needs_master = None
            self.unread = 0
            self._changed(now)

    def set_handler(self, handler: Handler, now: datetime) -> None:
        """Кто отвечает клиенту."""
        if handler is not self.handler:
            self.handler = handler
            self._changed(now)

    def mark_read(self, now: datetime) -> None:
        """Мастер прочитал диалог."""
        if self.unread:
            self.unread = 0
            self._changed(now)

    def visit_completed(self, now: datetime) -> None:
        """Состоялся ещё один визит клиента."""
        self.completed_visits += 1
        self._changed(now)

    def _changed(self, now: datetime) -> None:
        self.updated_at = now
        if not any(isinstance(event, ConversationChanged) for event in self._pending_events):
            self._record(
                ConversationChanged(occurred_at=now, conversation_id=self.id, master_id=self.master_id)
            )


def preview(content: MessageContent) -> str:
    """Строка для списка чатов."""
    match content:
        case TextContent(text) | SlotOfferContent(text, _, _) | SystemContent(text, _):
            short = text
        case VoiceContent():
            short = "Голосовое сообщение"
        case BookingCardContent(_, _, appointment):
            service = appointment.get("service")
            title = service.get("title") if isinstance(service, dict) else None
            short = f"Заявка: {title}" if title else "Заявка на запись"
    return short if len(short) <= PREVIEW_LENGTH else short[: PREVIEW_LENGTH - 1] + "…"
