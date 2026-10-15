"""Стратегии задержки повторных попыток."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta


class BackoffStrategy(ABC):
    """Задержка перед следующей попыткой."""

    @abstractmethod
    def delay(self, attempt: int) -> timedelta:
        """Задержка после неудачной попытки номер ``attempt`` (с единицы)."""


class ExponentialBackoff(BackoffStrategy):
    """Экспоненциальная задержка с потолком."""

    def __init__(
        self, base: timedelta = timedelta(seconds=10), ceiling: timedelta = timedelta(minutes=30)
    ) -> None:
        """Задать базу и потолок."""
        self._base = base
        self._ceiling = ceiling

    def delay(self, attempt: int) -> timedelta:
        """``base * 2^(attempt-1)``, но не больше потолка."""
        grown: timedelta = self._base * (2 ** max(attempt - 1, 0))
        return min(self._ceiling, grown)
