"""Реестр обработчиков отложенных задач (выбор стратегии по ``kind``)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar


class JobHandler(ABC):
    """Обработчик задач одного вида.

    Обработчик должен быть идемпотентным: аренда могла истечь посреди выполнения, и
    задачу взял другой воркер. Типичный обработчик перечитывает состояние агрегата и
    проверяет, актуальна ли задача (например, не отменена ли запись).
    """

    kind: ClassVar[str]

    @abstractmethod
    async def handle(self, payload: Mapping[str, Any]) -> None:
        """Выполнить задачу; исключение — повторить позже."""


class UnknownJobKindError(LookupError):
    """Для вида задачи не зарегистрирован обработчик."""


class JobHandlerRegistry:
    """Сопоставляет вид задачи и обработчик."""

    def __init__(self, handlers: tuple[JobHandler, ...] = ()) -> None:
        """Зарегистрировать начальный набор обработчиков."""
        self._handlers: dict[str, JobHandler] = {}
        for handler in handlers:
            self.register(handler)

    def register(self, handler: JobHandler) -> None:
        """Добавить обработчик (дубликат вида — ошибка конфигурации)."""
        if handler.kind in self._handlers:
            raise ValueError(f"Обработчик задач '{handler.kind}' уже зарегистрирован")
        self._handlers[handler.kind] = handler

    def get(self, kind: str) -> JobHandler:
        """Найти обработчик по виду."""
        try:
            return self._handlers[kind]
        except KeyError as error:
            raise UnknownJobKindError(kind) from error
