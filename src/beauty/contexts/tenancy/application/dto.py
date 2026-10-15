"""DTO — результаты запросов Tenancy для слоя представления."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ServiceView:
    """Услуга на странице мастера."""

    id: UUID
    title: str
    duration_min: int
    price_amount: int | None


@dataclass(frozen=True, slots=True)
class PhotoView:
    """Фото работы."""

    id: UUID
    url: str
    alt: str


@dataclass(frozen=True, slots=True)
class MasterPageView:
    """Публичная страница мастера."""

    id: UUID
    slug: str
    display_name: str
    name_nominative: str
    name_genitive: str
    name_dative: str
    specialty: str
    address: str
    timezone: str
    avatar_url: str | None
    about: str
    services: tuple[ServiceView, ...]
    photos: tuple[PhotoView, ...]
    confirm_within_hours: int
    change_deadline_hours: int


@dataclass(frozen=True, slots=True)
class SlotView:
    """Свободное окно (время — в поясе мастера)."""

    start: datetime
    end: datetime
    service_id: UUID
