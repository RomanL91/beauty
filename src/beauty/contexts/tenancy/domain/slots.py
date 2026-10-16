"""Поиск свободных окон мастера (доменный сервис).

Окна считаются на лету из правил, а не хранятся: расписание, выходные и занятость
меняются, а материализованные окна пришлось бы постоянно пересчитывать.

Алгоритм для каждого локального дня мастера в окне поиска:

1. рабочие интервалы дня недели (выходные даты пропускаются);
2. минус занятые интервалы (записи, заявки с удержанием — их даёт порт
   ``BusyTimeSource`` из контекста записи);
3. кандидаты — по сетке ``slot_step_minutes`` от начала рабочего интервала; окно
   подходит, если ``[start, start + длительность)`` целиком внутри свободного куска.

Арифметика — в UTC, локальное время нужно только чтобы построить границы
рабочих интервалов: так переход на летнее время не ломает длительности.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from beauty.contexts.tenancy.domain.value_objects import BookingRules, WeeklySchedule


@dataclass(frozen=True, slots=True)
class TimeInterval:
    """Полуинтервал ``[start, end)`` в абсолютном времени (aware datetime)."""

    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class Availability:
    """Снимок того, когда мастер принимает: пояс, расписание, выходные, правила."""

    timezone: ZoneInfo
    schedule: WeeklySchedule
    days_off: frozenset[date]
    rules: BookingRules


@dataclass(frozen=True, slots=True)
class SlotSearch:
    """Параметры поиска.

    ``window_from``/``window_to`` — запрошенные границы (``None`` — от «сейчас» и до
    горизонта записи).
    """

    duration: timedelta
    now: datetime
    window_from: datetime | None = None
    window_to: datetime | None = None
    limit: int = 20


class SlotFinder:
    """Свободные окна по снимку доступности и занятому времени."""

    def find(
        self, availability: Availability, search: SlotSearch, busy: Sequence[TimeInterval]
    ) -> list[TimeInterval]:
        """Окна по возрастанию времени (не больше ``limit``), время — в поясе мастера."""
        earliest, latest = self.bounds(availability, search)
        if earliest >= latest or search.limit <= 0:
            return []
        occupied = sorted(busy, key=lambda b: b.start)
        slots: list[TimeInterval] = []
        for slot in self._candidates(availability, search.duration, earliest, latest, occupied):
            slots.append(slot)
            if len(slots) >= search.limit:
                break
        return slots

    def bounds(self, availability: Availability, search: SlotSearch) -> tuple[datetime, datetime]:
        """Эффективное окно поиска: не раньше min notice и не позже горизонта записи."""
        # Всё в UTC: у aware-datetime с одним ZoneInfo Python сравнивает «настенное» время.
        tz = availability.timezone
        rules = availability.rules
        now = search.now.astimezone(UTC)
        not_before = now + timedelta(minutes=rules.min_notice_minutes)
        today = now.astimezone(tz).date()
        horizon = _local_midnight(today + timedelta(days=rules.horizon_days + 1), tz)
        earliest = max(not_before, search.window_from.astimezone(UTC)) if search.window_from else not_before
        latest = min(horizon, search.window_to.astimezone(UTC)) if search.window_to else horizon
        return earliest, latest

    def _candidates(
        self,
        availability: Availability,
        duration: timedelta,
        earliest: datetime,
        latest: datetime,
        busy: Sequence[TimeInterval],
    ) -> Iterator[TimeInterval]:
        tz = availability.timezone
        step = timedelta(minutes=availability.rules.slot_step_minutes)
        day = earliest.astimezone(tz).date()
        last_day = latest.astimezone(tz).date()
        while day <= last_day:
            if day not in availability.days_off:
                for hours in availability.schedule.hours_on(day.weekday()):
                    work = TimeInterval(_at(day, hours.start, tz), _at(day, hours.end, tz))
                    for free in _subtract(work, busy):
                        yield from self._grid(work.start, free, duration, step, earliest, latest, tz)
            day += timedelta(days=1)

    @staticmethod
    def _grid(
        anchor: datetime,
        free: TimeInterval,
        duration: timedelta,
        step: timedelta,
        earliest: datetime,
        latest: datetime,
        tz: ZoneInfo,
    ) -> Iterator[TimeInterval]:
        """Окна по сетке, привязанной к началу рабочего интервала."""
        lower = max(free.start, earliest)
        offset = lower - anchor
        steps = -(-offset // step) if offset > timedelta(0) else 0
        start = anchor + step * steps
        while start + duration <= free.end and start < latest:
            yield TimeInterval(start.astimezone(tz), (start + duration).astimezone(tz))
            start += step


def _local_midnight(day: date, tz: ZoneInfo) -> datetime:
    """Начало локального дня в UTC."""
    return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)


def _at(day: date, moment: time, tz: ZoneInfo) -> datetime:
    """Локальные дата и время мастера → момент в UTC.

    Несуществующее локальное время (перевод часов вперёд) нормализуется через UTC.
    """
    local = datetime.combine(day, moment, tzinfo=tz)
    return local.astimezone(UTC)


def _subtract(work: TimeInterval, busy: Sequence[TimeInterval]) -> Iterator[TimeInterval]:
    """Свободные куски рабочего интервала за вычетом занятых (занятые отсортированы)."""
    cursor = work.start
    for block in busy:
        if block.end <= cursor or block.start >= work.end:
            continue
        if block.start > cursor:
            yield TimeInterval(cursor, min(block.start, work.end))
        cursor = max(cursor, block.end)
        if cursor >= work.end:
            return
    if cursor < work.end:
        yield TimeInterval(cursor, work.end)
