"""Pydantic-схемы ответов публичного API Tenancy (по контракту ``MasterPage``, ``Slot``)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from beauty.contexts.tenancy.application.dto import MasterPageView, SlotView


class MoneyResponse(BaseModel):
    """Сумма в тиынах."""

    amount: int
    currency: Literal["KZT"] = "KZT"


class ServiceResponse(BaseModel):
    """Услуга."""

    id: UUID
    title: str
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
