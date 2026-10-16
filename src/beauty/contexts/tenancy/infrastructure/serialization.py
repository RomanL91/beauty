"""JSON-представление value objects Tenancy в колонках ``jsonb``."""

from __future__ import annotations

from datetime import date, time
from typing import Any
from uuid import UUID

from beauty.contexts.tenancy.domain.value_objects import PortfolioPhoto, WeeklySchedule, WorkingHours


def dump_schedule(schedule: WeeklySchedule) -> dict[str, list[list[str]]]:
    """``{"0": [["10:00", "15:00"], ...]}`` — ключ — день недели (0 — пн)."""
    return {
        str(day): [[f"{h.start:%H:%M}", f"{h.end:%H:%M}"] for h in hours]
        for day, hours in schedule.days.items()
    }


def load_schedule(raw: dict[str, list[list[str]]]) -> WeeklySchedule:
    """Обратное к ``dump_schedule``."""
    return WeeklySchedule(
        {
            int(day): tuple(
                WorkingHours(time.fromisoformat(start), time.fromisoformat(end)) for start, end in hours
            )
            for day, hours in raw.items()
        }
    )


def dump_days(days: tuple[date, ...]) -> list[str]:
    """Даты ISO."""
    return [d.isoformat() for d in days]


def load_days(raw: list[str]) -> tuple[date, ...]:
    """Обратное к ``dump_days``."""
    return tuple(date.fromisoformat(d) for d in raw)


def dump_photos(photos: tuple[PortfolioPhoto, ...]) -> list[dict[str, str]]:
    """Список фото."""
    return [{"id": str(p.id), "url": p.url, "alt": p.alt} for p in photos]


def load_photos(raw: list[dict[str, Any]]) -> tuple[PortfolioPhoto, ...]:
    """Обратное к ``dump_photos``."""
    return tuple(PortfolioPhoto(UUID(str(p["id"])), str(p["url"]), str(p.get("alt", ""))) for p in raw)
