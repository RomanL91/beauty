"""Базовые доменные исключения.

У каждого исключения есть машинно-читаемый ``code``: по нему слой представления
выбирает HTTP-статус или текст ответа в боте, не завязываясь на имена классов.
"""

from __future__ import annotations

from typing import ClassVar


class DomainError(Exception):
    """Нарушение бизнес-правила."""

    code: ClassVar[str] = "domain_error"

    def __init__(self, message: str | None = None) -> None:
        """Создать исключение с человеко-читаемым сообщением."""
        super().__init__(message or self.__class__.__doc__ or self.code)


class InvariantViolation(DomainError):
    """Операция привела бы агрегат в недопустимое состояние."""

    code = "invariant_violation"
