"""Порты прикладного слоя Conversations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from beauty.contexts.conversations.application.dto import (
    ConversationState,
    ConversationSummaryView,
    ConversationView,
    FeedRead,
    InboxView,
    MessagePageView,
    MessageView,
)
from beauty.contexts.conversations.domain.content import OfferedSlot


@dataclass(frozen=True, slots=True)
class ServiceInfo:
    """Услуга мастера."""

    id: UUID
    title: str
    duration_min: int


@dataclass(frozen=True, slots=True)
class MasterInfo:
    """Мастер глазами переписки."""

    id: UUID
    slug: str
    timezone: str
    name: str
    services: tuple[ServiceInfo, ...]

    def service(self, service_id: UUID | None) -> ServiceInfo | None:
        """Услуга по id; без id — самая короткая (как в поиске окон)."""
        if service_id is not None:
            return next((s for s in self.services if s.id == service_id), None)
        return min(self.services, key=lambda s: s.duration_min, default=None)


class ClientContacts(ABC):
    """Контакты клиентов (Identity)."""

    @abstractmethod
    async def phone(self, client_id: UUID) -> str:
        """Телефон клиента в E.164."""


class MasterCatalog(ABC):
    """Опубликованные мастера и их окна (Tenancy)."""

    @abstractmethod
    async def by_slug(self, slug: str) -> MasterInfo | None:
        """Мастер по адресу страницы."""

    @abstractmethod
    async def by_id(self, master_id: UUID) -> MasterInfo | None:
        """Мастер по id."""

    @abstractmethod
    async def free_slots(
        self, master_id: UUID, service_id: UUID, window_from: datetime | None, limit: int
    ) -> list[OfferedSlot]:
        """Ближайшие свободные окна для услуги."""


@dataclass(frozen=True, slots=True)
class RequestedAppointment:
    """Заявка, созданная Booking: снимок в форме контракта и его ревизия."""

    appointment_id: UUID
    revision: int
    appointment: Mapping[str, Any]


class BookingDesk(ABC):
    """Заявки на запись (Booking)."""

    @abstractmethod
    async def request(
        self, master_id: UUID, client_id: UUID, service_id: UUID, start: datetime
    ) -> RequestedAppointment:
        """Создать заявку или ``SlotNotAvailableError``."""


class ConversationReader(ABC):
    """Read-модель переписки (SQL → DTO)."""

    @abstractmethod
    async def find(self, master_id: UUID, client_id: UUID) -> ConversationView | None:
        """Переписка клиента с мастером."""

    @abstractmethod
    async def state(self, conversation_id: UUID) -> ConversationState | None:
        """Мастер, клиент и обработчик переписки."""

    @abstractmethod
    async def ids_for(self, master_id: UUID, client_ids: frozenset[UUID]) -> dict[UUID, UUID]:
        """Клиент → id переписки с мастером."""

    @abstractmethod
    async def page(
        self, conversation_id: UUID, client_id: UUID, before: UUID | None, limit: int
    ) -> MessagePageView | None:
        """Страница истории своей переписки (``None`` — нет такой)."""

    @abstractmethod
    async def feed(self, conversation_id: UUID, client_id: UUID, after: int | None) -> FeedRead | None:
        """События ленты после ``after`` (``None`` — нет такой переписки)."""


class InboxReader(ABC):
    """Чаты мастера (SQL → DTO)."""

    @abstractmethod
    async def inbox(self, master_id: UUID, filter_by: str, query: str | None) -> InboxView:
        """Чаты по фильтру (``all|needs_me|agent|me``) и поиску; счётчики — без учёта поиска."""

    @abstractmethod
    async def summary(self, master_id: UUID, conversation_id: UUID) -> ConversationSummaryView | None:
        """Шапка диалога своего мастера."""

    @abstractmethod
    async def master_message(self, master_id: UUID, message_id: UUID) -> tuple[UUID, MessageView] | None:
        """Сообщение переписки своего мастера и id переписки."""

    @abstractmethod
    async def master_page(
        self, conversation_id: UUID, master_id: UUID, before: UUID | None, limit: int
    ) -> MessagePageView | None:
        """История диалога своего мастера."""
