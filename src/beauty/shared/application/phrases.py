"""Даты и время по-русски (в поясе мастера) для текстов администратора и уведомлений."""

from __future__ import annotations

from datetime import date, datetime, timedelta

_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def day_label(day: date) -> str:
    """«пт, 17 октября»."""
    return f"{_WEEKDAYS[day.weekday()]}, {day.day} {_MONTHS[day.month - 1]}"


def day_phrase(day: date, today: date) -> str:
    """«сегодня», «завтра» или «в пт, 17 октября»."""
    if day == today:
        return "сегодня"
    if day == today + timedelta(days=1):
        return "завтра"
    return f"в {day_label(day)}"


def time_label(moment: datetime) -> str:
    """«10:30» (время — уже в поясе мастера)."""
    return f"{moment:%H:%M}"


def capitalize(text: str) -> str:
    """Первая буква — заглавная."""
    return text[:1].upper() + text[1:]
