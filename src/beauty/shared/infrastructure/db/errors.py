"""Перевод ошибок СУБД в прикладные ошибки."""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from beauty.shared.application.errors import ConcurrencyConflictError

UNIQUE_VIOLATION = "23505"
EXCLUSION_VIOLATION = "23P01"
SERIALIZATION_FAILURE = "40001"
DEADLOCK_DETECTED = "40P01"


class DatabaseErrorTranslator:
    """Распознаёт ошибки, означающие гонку параллельных транзакций.

    * ``StaleDataError`` — сработала оптимистичная блокировка (``version``);
    * ``unique_violation`` — две транзакции одновременно создали «одно и то же»;
    * ``serialization_failure`` / ``deadlock_detected`` — СУБД сама просит повторить.

    Нарушение исключающего ограничения (``exclusion_violation``) намеренно не
    считается гонкой: это бизнес-конфликт (слот уже занят), его переводит контекст.
    """

    _RETRYABLE_SQLSTATES = frozenset({UNIQUE_VIOLATION, SERIALIZATION_FAILURE, DEADLOCK_DETECTED})

    def translate(self, error: Exception) -> Exception:
        """Вернуть прикладную ошибку или исходное исключение."""
        if isinstance(error, StaleDataError):
            return ConcurrencyConflictError("Агрегат изменён параллельной транзакцией")
        if isinstance(error, DBAPIError) and self.sqlstate(error) in self._RETRYABLE_SQLSTATES:
            return ConcurrencyConflictError(f"Конфликт параллельных транзакций: {self.sqlstate(error)}")
        return error

    @staticmethod
    def sqlstate(error: DBAPIError) -> str | None:
        """Достать SQLSTATE из исключения драйвера."""
        original = error.orig
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(original, attribute, None)
            if value:
                return str(value)
        cause = getattr(original, "__cause__", None)
        value = getattr(cause, "sqlstate", None)
        return str(value) if value else None

    @staticmethod
    def constraint_name(error: IntegrityError) -> str | None:
        """Имя нарушенного ограничения (если драйвер его сообщил)."""
        original = error.orig
        for candidate in (original, getattr(original, "__cause__", None)):
            name = getattr(candidate, "constraint_name", None)
            if name:
                return str(name)
        return None
