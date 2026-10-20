"""DTO Clientbook — список и карточка клиента для кабинета и агента."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ClientRow:
    """Клиент в списке мастера."""

    client_id: UUID
    conversation_id: UUID
    display_name: str
    named: bool
    phone_masked: str
    visits: int
    last_visit_at: datetime | None
    next_visit_at: datetime | None
    notes: int
    last_activity_at: datetime


@dataclass(frozen=True, slots=True)
class ClientPage:
    """Страница списка."""

    items: tuple[ClientRow, ...]
    total: int


@dataclass(frozen=True, slots=True)
class ClientVisit:
    """Заявка или запись клиента."""

    id: UUID
    status: str
    start: datetime
    end: datetime
    service_title: str
    price_amount: int | None
    cancelled_by: str | None


@dataclass(frozen=True, slots=True)
class NoteView:
    """Заметка."""

    id: UUID
    text: str
    author: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ClientCardView:
    """Карточка клиента."""

    row: ClientRow
    since: datetime
    cancelled: int
    upcoming: tuple[ClientVisit, ...]
    history: tuple[ClientVisit, ...]
    notes: tuple[NoteView, ...]
