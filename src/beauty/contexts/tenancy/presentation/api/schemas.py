"""Pydantic-схемы API Tenancy: публичная страница и окна, настройки страницы в кабинете."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from beauty.contexts.tenancy.application.dto import MasterPageView, MasterSettingsView, SlotView


class MoneyResponse(BaseModel):
    """Сумма в тиынах."""

    amount: int
    currency: Literal["KZT"] = "KZT"


class ServiceResponse(BaseModel):
    """Услуга."""

    id: UUID
    title: str
    description: str
    duration_min: int
    price: MoneyResponse | None


class PhotoResponse(BaseModel):
    """Фото работы."""

    id: UUID
    url: str
    alt: str


class NameFormsResponse(BaseModel):
    """Имя мастера в падежах."""

    nominative: str
    genitive: str
    dative: str


class BookingRulesResponse(BaseModel):
    """Публичные правила записи."""

    confirm_within_hours: int
    change_deadline_hours: int


class MasterPageResponse(BaseModel):
    """Публичная страница мастера."""

    slug: str
    display_name: str
    name_forms: NameFormsResponse
    specialty: str
    address: str
    timezone: str
    avatar_url: str | None
    about: str
    services: list[ServiceResponse]
    photos: list[PhotoResponse]
    booking_rules: BookingRulesResponse

    @classmethod
    def of(cls, view: MasterPageView) -> MasterPageResponse:
        """Из DTO."""
        return cls(
            slug=view.slug,
            display_name=view.display_name,
            name_forms=NameFormsResponse(
                nominative=view.name_nominative, genitive=view.name_genitive, dative=view.name_dative
            ),
            specialty=view.specialty,
            address=view.address,
            timezone=view.timezone,
            avatar_url=view.avatar_url,
            about=view.about,
            services=[
                ServiceResponse(
                    id=s.id,
                    title=s.title,
                    description=s.description,
                    duration_min=s.duration_min,
                    price=None if s.price_amount is None else MoneyResponse(amount=s.price_amount),
                )
                for s in view.services
            ],
            photos=[PhotoResponse(id=p.id, url=p.url, alt=p.alt) for p in view.photos],
            booking_rules=BookingRulesResponse(
                confirm_within_hours=view.confirm_within_hours,
                change_deadline_hours=view.change_deadline_hours,
            ),
        )


class SlotResponse(BaseModel):
    """Свободное окно; время — в поясе мастера (RFC 3339 со смещением)."""

    start: datetime
    end: datetime
    service_id: UUID


class SlotsResponse(BaseModel):
    """Окна по возрастанию времени."""

    items: list[SlotResponse]

    @classmethod
    def of(cls, slots: list[SlotView]) -> SlotsResponse:
        """Из DTO."""
        return cls(items=[SlotResponse(start=s.start, end=s.end, service_id=s.service_id) for s in slots])


# ─────────────────────────── кабинет: настройки страницы ───────────────────────────


class TimeIntervalModel(BaseModel):
    """Интервал рабочего дня ``HH:MM``."""

    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")


class WorkingDayModel(BaseModel):
    """Рабочий день недели (0 — понедельник)."""

    weekday: int = Field(ge=0, le=6)
    intervals: list[TimeIntervalModel] = Field(min_length=1, max_length=8)


class BookingRulesSettingsModel(BaseModel):
    """Все правила записи."""

    confirm_within_hours: int
    change_deadline_hours: int
    min_notice_minutes: int
    horizon_days: int
    slot_step_minutes: int


class MasterSettingsResponse(BaseModel):
    """``MasterSettings`` контракта."""

    page: MasterPageResponse
    status: Literal["draft", "published"]
    published_at: datetime | None
    working_hours: list[WorkingDayModel]
    days_off: list[date]
    booking_rules: BookingRulesSettingsModel
    publish_blockers: list[str]

    @classmethod
    def of(cls, view: MasterSettingsView) -> MasterSettingsResponse:
        """Из DTO."""
        return cls(
            page=MasterPageResponse.of(view.page),
            status="published" if view.published else "draft",
            published_at=view.published_at,
            working_hours=[
                WorkingDayModel(
                    weekday=weekday,
                    intervals=[
                        TimeIntervalModel(start=f"{start:%H:%M}", end=f"{end:%H:%M}") for start, end in hours
                    ],
                )
                for weekday, hours in view.working_hours
            ],
            days_off=list(view.days_off),
            booking_rules=BookingRulesSettingsModel(
                confirm_within_hours=view.page.confirm_within_hours,
                change_deadline_hours=view.page.change_deadline_hours,
                min_notice_minutes=view.min_notice_minutes,
                horizon_days=view.horizon_days,
                slot_step_minutes=view.slot_step_minutes,
            ),
            publish_blockers=list(view.publish_blockers),
        )


class ProfileInput(BaseModel):
    """``ProfileInput`` контракта."""

    display_name: str = Field(min_length=1, max_length=80)
    name_forms: NameFormsResponse
    specialty: str = Field(max_length=80)
    address: str = Field(max_length=200)
    about: str = Field(max_length=4000)
    timezone: str = Field(max_length=64)


class ServiceInput(BaseModel):
    """``ServiceInput`` контракта."""

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    duration_min: int
    price: MoneyResponse | None


class WorkingHoursInput(BaseModel):
    """Рабочие часы по дням недели."""

    days: list[WorkingDayModel] = Field(max_length=7)


class DaysOffInput(BaseModel):
    """Выходные даты."""

    days: list[date] = Field(max_length=366)
