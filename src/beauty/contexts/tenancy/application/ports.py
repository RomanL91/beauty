"""Порты прикладного слоя Tenancy: read-модели и занятое время."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from beauty.contexts.tenancy.application.dto import MasterPageView
from beauty.contexts.tenancy.domain.slots import Availability, TimeInterval

type MasterRef = str | UUID
"""Ссылка на мастера: адрес страницы (slug) или id."""


class MasterPageReader(ABC):
    """Публичная страница мастера (SQL → DTO, без агрегата)."""

    @abstractmethod
    async def read(self, master: MasterRef, *, published_only: bool = True) -> MasterPageView | None:
        """Страница мастера (по умолчанию — только опубликованного) или ``None``."""


@dataclass(frozen=True, slots=True)
class BookableService:
    """Услуга, на которую можно записаться."""

    id: UUID
    duration_min: int


@dataclass(frozen=True, slots=True)
class AvailabilityRecord:
    """Всё, что нужно для поиска окон опубликованного мастера."""

    master_id: UUID
    availability: Availability
    services: tuple[BookableService, ...]


class AvailabilityReader(ABC):
    """Снимок доступности мастера."""

    @abstractmethod
    async def read(self, master: MasterRef, *, published_only: bool = True) -> AvailabilityRecord | None:
        """Снимок мастера (по умолчанию — только опубликованного) или ``None``."""


class BusyTimeSource(ABC):
    """Занятое время мастера: записи и заявки с удержанием.

    Реализует контекст записи; пока записей нет, подключается пустой источник.
    """

    @abstractmethod
    async def busy(self, master_id: UUID, start: datetime, end: datetime) -> list[TimeInterval]:
        """Занятые интервалы, пересекающие ``[start, end)``."""


class MasterDirectory(ABC):
    """Поиск мастера по адресу страницы (для администрирования, включая черновики)."""

    @abstractmethod
    async def find_id(self, slug: str) -> UUID | None:
        """Id мастера с таким slug."""

    @abstractmethod
    async def find_by_owner(self, phone: str) -> UUID | None:
        """Id мастера по телефону владельца."""

    @abstractmethod
    async def active_service_titles(self, master_id: UUID) -> frozenset[str]:
        """Названия активных услуг (черновика тоже)."""

    @abstractmethod
    async def removed_service_titles(self, master_id: UUID, since: datetime) -> tuple[str, ...]:
        """Названия услуг, убранных с ``since`` (свежие первыми), которых нет среди активных."""
