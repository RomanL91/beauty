"""Прикладные ошибки.

Они описывают исход сценария (не найдено, нет доступа, конфликт), а не нарушение
предметного правила. Слой представления переводит их в ответы по полю ``code``.
"""

from __future__ import annotations

from typing import ClassVar


class ApplicationError(Exception):
    """Базовая ошибка прикладного слоя."""

    code: ClassVar[str] = "application_error"

    def __init__(self, message: str | None = None) -> None:
        """Создать ошибку с сообщением (по умолчанию — докстринг класса)."""
        super().__init__(message or self.__class__.__doc__ or self.code)


class NotFoundError(ApplicationError):
    """Запрошенный объект не найден."""

    code = "not_found"


class AccessDeniedError(ApplicationError):
    """Недостаточно прав для операции."""

    code = "access_denied"


class ConflictError(ApplicationError):
    """Операция конфликтует с текущим состоянием."""

    code = "conflict"


class ConcurrencyConflictError(ConflictError):
    """Параллельная транзакция изменила те же данные; операцию можно повторить."""

    code = "concurrency_conflict"
