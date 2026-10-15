"""Стандартные middleware медиатора."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

from beauty.shared.application.cqrs import Command, Request
from beauty.shared.application.errors import ConcurrencyConflictError
from beauty.shared.application.mediator import Middleware, NextStep

logger = logging.getLogger(__name__)


class LoggingMiddleware(Middleware):
    """Логирует тип сообщения, длительность и исход обработки."""

    async def __call__(self, message: Request[Any], next_step: NextStep) -> Any:
        """Замерить и залогировать обработку."""
        started = time.perf_counter()
        name = type(message).__name__
        try:
            result = await next_step(message)
        except Exception:
            logger.info("%s завершилась ошибкой за %.1f мс", name, (time.perf_counter() - started) * 1000)
            raise
        logger.debug("%s обработана за %.1f мс", name, (time.perf_counter() - started) * 1000)
        return result


class ConcurrencyRetryMiddleware(Middleware):
    """Повторяет команду при конфликте конкурентности.

    Конфликт (оптимистичная блокировка, нарушение уникальности при гонке создания)
    означает, что параллельная транзакция успела раньше. Повтор с новым Unit of Work
    перечитает актуальное состояние. Задержка — экспонента с полным джиттером, чтобы
    конкурирующие корутины не повторяли попытки синхронно. Запросы не повторяются:
    они ничего не пишут и конфликтов не порождают.
    """

    def __init__(self, attempts: int = 3, base_delay: float = 0.02, max_delay: float = 0.5) -> None:
        """Настроить число попыток и границы задержки (секунды)."""
        if attempts < 1:
            raise ValueError("attempts должно быть >= 1")
        self._attempts = attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._random = random.SystemRandom()

    async def __call__(self, message: Request[Any], next_step: NextStep) -> Any:
        """Выполнить команду, повторяя её при ``ConcurrencyConflictError``."""
        if not isinstance(message, Command):
            return await next_step(message)
        for attempt in range(1, self._attempts + 1):
            try:
                return await next_step(message)
            except ConcurrencyConflictError:
                if attempt == self._attempts:
                    raise
                ceiling = min(self._max_delay, self._base_delay * 2 ** (attempt - 1))
                await asyncio.sleep(self._random.uniform(0, ceiling))
        raise AssertionError("недостижимо")  # pragma: no cover
