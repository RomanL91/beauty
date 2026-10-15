"""Источник текущего времени.

Домен никогда не вызывает ``datetime.now()`` напрямую: время передаётся в методы
агрегатов явно, а приложение получает его из ``Clock``. Это делает правила, зависящие
от времени (TTL, дедлайны отмены), детерминированно тестируемыми.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime


class Clock(ABC):
    """Порт часов."""

    @abstractmethod
    def now(self) -> datetime:
        """Вернуть текущий момент в UTC (aware datetime)."""


class SystemClock(Clock):
    """Системные часы."""

    def now(self) -> datetime:
        """Вернуть текущее время ОС в UTC."""
        return datetime.now(UTC)
