"""Фейковые данные мастера для MCP-заглушки (клиенты, услуги, слоты)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FakeClient:
    """Клиент мастера."""

    card_id: str
    name: str
    phone: str


@dataclass(frozen=True, slots=True)
class FakeService:
    """Услуга мастера."""

    name: str
    minutes: int
    price: int


CLIENTS: tuple[FakeClient, ...] = (
    FakeClient("card-daria-1", "Дарья", "+77015558967"),
    FakeClient("card-daria-2", "Дарья", "+77019991234"),
    FakeClient("card-oksana", "Оксана", "+77012223344"),
    FakeClient("card-alina", "Алина", "+77017776655"),
)

SERVICES: tuple[FakeService, ...] = (
    FakeService("Классический массаж спины", 60, 12000),
    FakeService("Антицеллюлитный массаж", 90, 18000),
)

FREE_SLOTS: tuple[str, ...] = ("2026-10-16T10:00", "2026-10-16T14:00", "2026-10-17T12:00")
BUSY_SLOTS: dict[str, str] = {"2026-10-17T12:00": "card-oksana"}
