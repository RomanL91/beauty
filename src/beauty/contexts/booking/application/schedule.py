"""График дня мастера: записи, перерывы и свободное время.

Сборка дня — чистая функция над рабочими часами (Tenancy) и записями дня (Booking):
свободное время = рабочие интервалы минус записи, перерыв = промежуток между
рабочими интервалами. Арифметика — в UTC, наружу время уходит в поясе мастера.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from itertools import pairwise
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

BREAK_TITLE = "Перерыв"


@dataclass(frozen=True, slots=True)
class CalendarDay:
    """Рабочий день: выходной или интервалы в локальном времени мастера."""

    date: date
    day_off: bool
    hours: tuple[tuple[time, time], ...]


@dataclass(frozen=True, slots=True)
class WorkingCalendar:
    """Пояс мастера и дни подряд."""

    timezone: str
    days: tuple[CalendarDay, ...]


@dataclass(frozen=True, slots=True)
class DayAppointment:
    """Запись дня: снимок для API, клиент и время (UTC)."""

    payload: Mapping[str, Any]
    client_id: UUID
    start: datetime
    end: datetime


def build_day(
    day: CalendarDay,
    zone: ZoneInfo,
    appointments: Sequence[DayAppointment],
    conversations: Mapping[UUID, UUID],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Элементы дня по времени и сводка."""
    timed: list[tuple[datetime, dict[str, Any]]] = []
    booked = sorted(appointments, key=lambda a: a.start)
    for appointment in booked:
        conversation = conversations.get(appointment.client_id)
        timed.append(
            (
                appointment.start,
                {
                    "kind": "appointment",
                    "appointment": dict(appointment.payload),
                    "conversation_id": None if conversation is None else str(conversation),
                },
            )
        )
    work = [(_at(day.date, start, zone), _at(day.date, end, zone)) for start, end in day.hours]
    free_minutes = 0
    for start, end in work:
        for free_start, free_end in _subtract(start, end, booked):
            free_minutes += int((free_end - free_start).total_seconds() // 60)
            timed.append((free_start, _span("free", free_start, free_end, zone)))
    for (_, previous_end), (next_start, _) in pairwise(work):
        if next_start > previous_end:
            item = _span("break", previous_end, next_start, zone) | {"title": BREAK_TITLE}
            timed.append((previous_end, item))
    timed.sort(key=lambda pair: pair[0])
    summary = {
        "appointments": len(booked),
        "pending_requests": sum(1 for a in booked if a.payload.get("status") == "requested"),
        "free_minutes": free_minutes,
    }
    return [item for _, item in timed], summary


def _at(day: date, moment: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, moment, tzinfo=zone).astimezone(UTC)


def _span(kind: str, start: datetime, end: datetime, zone: ZoneInfo) -> dict[str, Any]:
    return {
        "kind": kind,
        "start": start.astimezone(zone).isoformat(),
        "end": end.astimezone(zone).isoformat(),
    }


def _subtract(
    start: datetime, end: datetime, booked: Sequence[DayAppointment]
) -> list[tuple[datetime, datetime]]:
    """Свободные куски ``[start, end)`` за вычетом записей (записи отсортированы)."""
    pieces: list[tuple[datetime, datetime]] = []
    cursor = start
    for appointment in booked:
        if appointment.end <= cursor or appointment.start >= end:
            continue
        if appointment.start > cursor:
            pieces.append((cursor, appointment.start))
        cursor = max(cursor, appointment.end)
    if cursor < end:
        pieces.append((cursor, end))
    return pieces
