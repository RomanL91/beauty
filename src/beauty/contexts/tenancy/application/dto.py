"""DTO — результаты запросов Tenancy для слоя представления."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
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


@dataclass(frozen=True, slots=True)
class BookableSlotView:
    """Проверенное окно для заявки: снимок услуги и правил мастера."""

    master_id: UUID
    service: ServiceView
    start: datetime
    end: datetime
    timezone: str
    confirm_within_hours: int
    change_deadline_hours: int


@dataclass(frozen=True, slots=True)
class CalendarDayView:
    """Рабочий день мастера: выходной или рабочие интервалы (локальное время)."""

    date: date
    day_off: bool
    hours: tuple[tuple[time, time], ...]


@dataclass(frozen=True, slots=True)
class WorkingCalendarView:
    """Рабочие дни мастера подряд, начиная с даты запроса."""

    timezone: str
    days: tuple[CalendarDayView, ...]


@dataclass(frozen=True, slots=True)
class MasterSettingsView:
    """Страница мастера глазами владельца: черновик, график, правила, что мешает публикации."""

    page: MasterPageView
    published: bool
    published_at: datetime | None
    working_hours: tuple[tuple[int, tuple[tuple[time, time], ...]], ...]
    days_off: tuple[date, ...]
    min_notice_minutes: int
    horizon_days: int
    slot_step_minutes: int
    publish_blockers: tuple[str, ...]
