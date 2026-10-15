"""Value objects контекста Tenancy."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import time, timedelta
from enum import StrEnum
from itertools import pairwise
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from beauty.contexts.tenancy.domain.errors import (
    InvalidBookingRules,
    InvalidMasterSlug,
    InvalidMoney,
    InvalidProfile,
    InvalidServiceDuration,
    InvalidTimeZone,
    InvalidWeeklySchedule,
)

_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
RESERVED_SLUGS = frozenset(
    {
        "www",
        "master",
        "masters",
        "api",
        "app",
        "admin",
        "static",
        "assets",
        "mail",
        "help",
        "support",
        "beautiful",
    }
)


class MasterStatus(StrEnum):
    """Видимость страницы мастера."""

    DRAFT = "draft"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class MasterSlug:
    """Адрес страницы мастера — поддомен ``<slug>.beautiful.kz``."""

    value: str

    def __post_init__(self) -> None:
        """Проверить формат и зарезервированные имена."""
        if len(self.value) < 2 or not _SLUG.match(self.value):
            raise InvalidMasterSlug(f"Некорректный адрес страницы: {self.value!r}")
        if self.value in RESERVED_SLUGS:
            raise InvalidMasterSlug(f"Адрес {self.value!r} зарезервирован платформой")


@dataclass(frozen=True, slots=True)
class NameForms:
    """Имя мастера в падежах для текстов интерфейса и агента.

    Склонять автоматически ненадёжно (особенно казахские имена), поэтому формы
    задаёт сам мастер: «**Алиса** ответит», «подтверждения **Алисы**», «запись к **Алисе**».
    """

    nominative: str
    genitive: str
    dative: str

    def __post_init__(self) -> None:
        """Все формы непустые и короткие."""
        for value in (self.nominative, self.genitive, self.dative):
            if not value.strip() or len(value) > 40:
                raise InvalidProfile("Формы имени — от 1 до 40 символов")


@dataclass(frozen=True, slots=True)
class TimeZoneName:
    """Часовой пояс IANA (``Asia/Almaty``)."""

    value: str

    def __post_init__(self) -> None:
        """Проверить, что пояс известен базе zoneinfo."""
        if self.value not in _known_zones():
            raise InvalidTimeZone(f"Неизвестный часовой пояс: {self.value!r}")

    def zone(self) -> ZoneInfo:
        """Объект часового пояса."""
        try:
            return ZoneInfo(self.value)
        except ZoneInfoNotFoundError as error:  # pragma: no cover - проверено в __post_init__
            raise InvalidTimeZone(self.value) from error


_ZONES: frozenset[str] | None = None


def _known_zones() -> frozenset[str]:
    """Список поясов (читается с диска один раз)."""
    global _ZONES  # noqa: PLW0603 - ленивый кэш модульного уровня
    if _ZONES is None:
        _ZONES = frozenset(available_timezones())
    return _ZONES


@dataclass(frozen=True, slots=True)
class ServiceDuration:
    """Длительность услуги в минутах."""

    minutes: int

    def __post_init__(self) -> None:
        """5–480 минут, кратно 5 (сетка окон не бывает мельче 5 минут)."""
        if not 5 <= self.minutes <= 480 or self.minutes % 5:
            raise InvalidServiceDuration(f"Недопустимая длительность: {self.minutes} мин")

    def as_timedelta(self) -> timedelta:
        """Длительность как ``timedelta``."""
        return timedelta(minutes=self.minutes)


@dataclass(frozen=True, slots=True)
class Money:
    """Сумма в минимальных единицах валюты (тиынах)."""

    amount: int
    currency: str = "KZT"

    def __post_init__(self) -> None:
        """Неотрицательная сумма в тенге."""
        if self.amount < 0:
            raise InvalidMoney("Цена не может быть отрицательной")
        if self.currency != "KZT":
            raise InvalidMoney(f"Валюта {self.currency!r} не поддерживается")


@dataclass(frozen=True, slots=True)
class BookingRules:
    """Правила записи к мастеру.

    Атрибуты:
        confirm_within_hours: за сколько часов мастер подтверждает заявку (её срок удержания).
        change_deadline_hours: перенос/отмена не позднее чем за N часов до визита.
        min_notice_minutes: ближайшее окно — не раньше чем через N минут.
        horizon_days: на сколько дней вперёд открыта запись.
        slot_step_minutes: шаг сетки окон.
    """

    confirm_within_hours: int = 2
    change_deadline_hours: int = 12
    min_notice_minutes: int = 60
    horizon_days: int = 30
    slot_step_minutes: int = 30

    ALLOWED_STEPS = frozenset({5, 10, 15, 20, 30, 60})

    def __post_init__(self) -> None:
        """Проверить диапазоны."""
        if not 1 <= self.confirm_within_hours <= 72:
            raise InvalidBookingRules("Срок подтверждения — от 1 до 72 часов")
        if not 0 <= self.change_deadline_hours <= 168:
            raise InvalidBookingRules("Срок переноса — от 0 до 168 часов")
        if not 0 <= self.min_notice_minutes <= 7 * 24 * 60:
            raise InvalidBookingRules("Минимальный интервал до визита — до 7 дней")
        if not 1 <= self.horizon_days <= 90:
            raise InvalidBookingRules("Горизонт записи — от 1 до 90 дней")
        if self.slot_step_minutes not in self.ALLOWED_STEPS:
            raise InvalidBookingRules(f"Шаг сетки — один из {sorted(self.ALLOWED_STEPS)} минут")


@dataclass(frozen=True, slots=True, order=True)
class WorkingHours:
    """Рабочий интервал дня в локальном времени мастера: ``[start, end)``."""

    start: time
    end: time

    def __post_init__(self) -> None:
        """Начало раньше конца, минуты кратны 5, без секунд и пояса."""
        for moment in (self.start, self.end):
            if moment.tzinfo is not None or moment.second or moment.microsecond or moment.minute % 5:
                raise InvalidWeeklySchedule("Время — часы и минуты, кратные 5, без пояса")
        if self.start >= self.end:
            raise InvalidWeeklySchedule(f"Интервал {self} пустой")

    def __str__(self) -> str:
        """``10:00–19:00``."""
        return f"{self.start:%H:%M}–{self.end:%H:%M}"


@dataclass(frozen=True, slots=True)
class WeeklySchedule:
    """Рабочие часы по дням недели (0 — понедельник … 6 — воскресенье).

    Промежуток между интервалами одного дня — перерыв. Работа через полночь не
    поддерживается: смену до 02:00 задают двумя интервалами в соседних днях.
    """

    days: dict[int, tuple[WorkingHours, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Нормализовать: пустые дни убрать, интервалы отсортировать и проверить пересечения."""
        normalized: dict[int, tuple[WorkingHours, ...]] = {}
        for weekday, hours in self.days.items():
            if weekday not in range(7):
                raise InvalidWeeklySchedule(f"Нет дня недели {weekday}")
            ordered = tuple(sorted(hours))
            for previous, current in pairwise(ordered):
                if current.start < previous.end:
                    raise InvalidWeeklySchedule(f"Интервалы {previous} и {current} пересекаются")
            if ordered:
                normalized[weekday] = ordered
        object.__setattr__(self, "days", normalized)

    def __hash__(self) -> int:
        """Хеш по содержимому (словарь сам по себе не хешируется)."""
        return hash(tuple(sorted(self.days.items())))

    @property
    def is_empty(self) -> bool:
        """Нет ни одного рабочего интервала."""
        return not self.days

    def hours_on(self, weekday: int) -> tuple[WorkingHours, ...]:
        """Интервалы дня недели."""
        return self.days.get(weekday, ())


@dataclass(frozen=True, slots=True)
class PortfolioPhoto:
    """Фото работы на странице мастера."""

    id: UUID
    url: str
    alt: str = ""

    def __post_init__(self) -> None:
        """Только https-ссылки."""
        if not self.url.startswith("https://") or len(self.url) > 2000:
            raise InvalidProfile("Фото — https-ссылка до 2000 символов")
