"""Поиск свободных окон."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from beauty.contexts.tenancy.domain.slots import Availability, SlotFinder, SlotSearch, TimeInterval
from beauty.contexts.tenancy.domain.value_objects import BookingRules, WeeklySchedule, WorkingHours

ALMATY = ZoneInfo("Asia/Almaty")  # UTC+5, без перехода на летнее время
FINDER = SlotFinder()


def local(day: int, hour: int, minute: int = 0, tz: ZoneInfo = ALMATY, month: int = 10) -> datetime:
    """Локальный момент 2026-10-<day> в поясе мастера."""
    return datetime(2026, month, day, hour, minute, tzinfo=tz)


def availability(
    hours: dict[int, tuple[WorkingHours, ...]] | None = None,
    *,
    rules: BookingRules | None = None,
    days_off: frozenset[date] = frozenset(),
    tz: ZoneInfo = ALMATY,
) -> Availability:
    """Пн–Сб 10:00–19:00 с перерывом 15:00–15:30, шаг 30 мин, min notice 0."""
    default = (WorkingHours(time(10), time(15)), WorkingHours(time(15, 30), time(19)))
    return Availability(
        timezone=tz,
        schedule=WeeklySchedule(hours if hours is not None else dict.fromkeys(range(6), default)),
        days_off=days_off,
        rules=rules or BookingRules(min_notice_minutes=0, slot_step_minutes=30, horizon_days=30),
    )


def starts(slots: list[TimeInterval]) -> list[str]:
    """Начала окон «dd HH:MM» в поясе Алматы."""
    return [s.start.astimezone(ALMATY).strftime("%d %H:%M") for s in slots]


def test_grid_breaks_and_duration() -> None:
    # Чт 15 окт, 09:00 — весь рабочий день впереди.
    search = SlotSearch(duration=timedelta(minutes=90), now=local(15, 9), window_to=local(16, 0))
    slots = FINDER.find(availability(), search, busy=[])
    assert starts(slots) == [
        "15 10:00",
        "15 10:30",
        "15 11:00",
        "15 11:30",
        "15 12:00",
        "15 12:30",
        "15 13:00",
        "15 13:30",
        "15 15:30",
        "15 16:00",
        "15 16:30",
        "15 17:00",
        "15 17:30",
    ]
    # Окно не пересекает перерыв и конец дня.
    assert all(s.end <= local(15, 15) or s.start >= local(15, 15, 30) for s in slots)
    assert slots[-1].end == local(15, 19)
    # Время отдаётся в поясе мастера.
    assert slots[0].start.utcoffset() == timedelta(hours=5)


def test_busy_intervals_are_excluded() -> None:
    search = SlotSearch(duration=timedelta(minutes=40), now=local(15, 9), window_to=local(15, 15))
    busy = [TimeInterval(local(15, 10), local(15, 11, 30)), TimeInterval(local(15, 12), local(15, 12, 40))]
    # 11:30–12:00 — 30 минут, услуга 40 не помещается; 14:30 + 40 залезает в перерыв.
    assert starts(FINDER.find(availability(), search, busy)) == ["15 13:00", "15 13:30", "15 14:00"]


def test_min_notice_and_limit() -> None:
    rules = BookingRules(min_notice_minutes=60, slot_step_minutes=30)
    search = SlotSearch(duration=timedelta(minutes=40), now=local(15, 13, 10), limit=3)
    # Не раньше 14:10: 14:30 + 40 мин залезает в перерыв 15:00–15:30.
    assert starts(FINDER.find(availability(rules=rules), search, [])) == ["15 15:30", "15 16:00", "15 16:30"]


def test_days_off_sunday_and_window() -> None:
    search = SlotSearch(
        duration=timedelta(minutes=60), now=local(15, 9), window_from=local(17, 18), window_to=local(20, 0)
    )
    found = starts(FINDER.find(availability(days_off=frozenset({date(2026, 10, 19)})), search, []))
    # Сб 17-го — с 18:00, Вс 18-го — выходной по расписанию, Пн 19-го — выходной датой.
    assert found == ["17 18:00"]


def test_horizon_limits_search() -> None:
    rules = BookingRules(min_notice_minutes=0, horizon_days=1, slot_step_minutes=60)
    search = SlotSearch(duration=timedelta(minutes=60), now=local(15, 17), limit=100)
    found = starts(FINDER.find(availability(rules=rules), search, []))
    # Сетка второго интервала — от 15:30; последнее окно дня 17:30–18:30.
    assert found[0] == "15 17:30"
    assert found[-1] == "16 17:30"
    assert all(day in {"15", "16"} for day in (f[:2] for f in found))


def test_empty_when_window_inverted() -> None:
    search = SlotSearch(
        duration=timedelta(minutes=30), now=local(15, 9), window_from=local(16, 0), window_to=local(15, 0)
    )
    assert FINDER.find(availability(), search, []) == []


def test_daylight_saving_transition() -> None:
    """Берлин, 29 марта 2026: в 02:00 часы переводят на 03:00 — день короче на час."""
    berlin = ZoneInfo("Europe/Berlin")
    hours = {6: (WorkingHours(time(1), time(5)),)}  # воскресенье
    search = SlotSearch(
        duration=timedelta(minutes=60),
        now=datetime(2026, 3, 28, 12, tzinfo=UTC),
        window_to=datetime(2026, 3, 30, tzinfo=UTC),
    )
    slots = FINDER.find(
        availability(hours, rules=BookingRules(min_notice_minutes=0, slot_step_minutes=60), tz=berlin),
        search,
        [],
    )
    # 01:00–05:00 местного = 3 часа реального времени → три часовых окна.
    assert [s.start.astimezone(berlin).strftime("%H:%M") for s in slots] == ["01:00", "03:00", "04:00"]
    # Разность в UTC: у aware-datetime с одним ZoneInfo Python вычитает «настенное» время.
    assert all(s.end.astimezone(UTC) - s.start.astimezone(UTC) == timedelta(hours=1) for s in slots)


def test_grid_resumes_after_busy_block() -> None:
    """После занятого куска окна идут по той же сетке от начала рабочего интервала."""
    search = SlotSearch(duration=timedelta(minutes=30), now=local(15, 9), window_to=local(15, 12))
    busy = [TimeInterval(local(15, 10), local(15, 10, 40))]
    assert starts(FINDER.find(availability(), search, busy)) == ["15 11:00", "15 11:30"]
