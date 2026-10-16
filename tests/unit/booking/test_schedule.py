"""Сборка дня мастера: записи, перерывы, свободное время, сводка."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from beauty.contexts.booking.application.schedule import CalendarDay, DayAppointment, build_day

ALMATY = ZoneInfo("Asia/Almaty")
DAY = date(2026, 10, 16)
WORK = CalendarDay(DAY, False, ((time(10), time(15)), (time(15, 30), time(19))))


def booked(start: time, end: time, status: str = "confirmed", client: int = 1) -> DayAppointment:
    """Запись дня (время — локальное)."""
    return DayAppointment(
        {"id": f"a-{start}", "status": status},
        UUID(int=client),
        datetime.combine(DAY, start, tzinfo=ALMATY).astimezone(UTC),
        datetime.combine(DAY, end, tzinfo=ALMATY).astimezone(UTC),
    )


def test_day_with_appointments_and_break() -> None:
    items, summary = build_day(
        WORK,
        ALMATY,
        [booked(time(12), time(13), "requested"), booked(time(10), time(11))],
        {UUID(int=1): UUID(int=9)},
    )
    assert [(i["kind"], i.get("start", "")[11:16]) for i in items] == [
        ("appointment", ""),
        ("free", "11:00"),
        ("appointment", ""),
        ("free", "13:00"),
        ("break", "15:00"),
        ("free", "15:30"),
    ]
    assert items[4]["title"] == "Перерыв"
    assert items[1]["start"] == "2026-10-16T11:00:00+05:00"
    assert items[0]["conversation_id"] == str(UUID(int=9))
    assert summary == {"appointments": 2, "pending_requests": 1, "free_minutes": 60 + 120 + 210}


def test_day_off_and_appointment_outside_hours() -> None:
    items, summary = build_day(CalendarDay(DAY, True, ()), ALMATY, [booked(time(20), time(21), client=2)], {})
    assert [i["kind"] for i in items] == ["appointment"]
    assert items[0]["conversation_id"] is None
    assert summary == {"appointments": 1, "pending_requests": 0, "free_minutes": 0}
