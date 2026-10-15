"""CQRS-абстракции: запросы на запись (команды), на чтение (запросы) и их обработчики.

Команда меняет состояние и выполняется через Unit of Work и агрегаты. Запрос ничего
не меняет и читает данные напрямую (SQL → DTO), минуя агрегаты: так чтение не тянет
лишние связи и не порождает N+1. Параметр типа ``R`` — тип результата, благодаря ему
``Mediator.send`` возвращает строго типизированное значение.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Request[R]:
    """Базовое сообщение для медиатора с типом результата ``R``."""


@dataclass(frozen=True, slots=True)
class Command[R](Request[R]):
    """Намерение изменить состояние системы."""


@dataclass(frozen=True, slots=True)
class Query[R](Request[R]):
    """Запрос на чтение без побочных эффектов."""


class Handler[M: Request[Any], R](ABC):
    """Обработчик сообщения ``M`` с результатом ``R``.

    Обработчик создаётся фабрикой на каждый вызов: так у каждой попытки (в том числе
    повторной после конфликта конкурентности) свой Unit of Work и своя сессия.
    """

    @abstractmethod
    async def handle(self, message: M) -> R:
        """Обработать сообщение."""
