"""Паттерн «Спецификация».

Бизнес-правило-предикат оформляется объектом, который можно комбинировать
операторами ``&``, ``|`` и ``~``. Так правила остаются именованными, тестируемыми
по отдельности и переиспользуемыми, а не размазываются условиями по сервисам.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Specification[T](ABC):
    """Предикат над кандидатом типа ``T``."""

    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """Проверить, удовлетворяет ли кандидат правилу."""

    def __and__(self, other: Specification[T]) -> Specification[T]:
        """Конъюнкция спецификаций."""
        return _AndSpecification(self, other)

    def __or__(self, other: Specification[T]) -> Specification[T]:
        """Дизъюнкция спецификаций."""
        return _OrSpecification(self, other)

    def __invert__(self) -> Specification[T]:
        """Отрицание спецификации."""
        return _NotSpecification(self)


class _AndSpecification[T](Specification[T]):
    """Обе спецификации должны выполняться."""

    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        """Запомнить операнды."""
        self._left, self._right = left, right

    def is_satisfied_by(self, candidate: T) -> bool:
        """Проверить обе части (с коротким замыканием)."""
        return self._left.is_satisfied_by(candidate) and self._right.is_satisfied_by(candidate)


class _OrSpecification[T](Specification[T]):
    """Достаточно выполнения одной из спецификаций."""

    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        """Запомнить операнды."""
        self._left, self._right = left, right

    def is_satisfied_by(self, candidate: T) -> bool:
        """Проверить хотя бы одну часть."""
        return self._left.is_satisfied_by(candidate) or self._right.is_satisfied_by(candidate)


class _NotSpecification[T](Specification[T]):
    """Отрицание спецификации."""

    def __init__(self, inner: Specification[T]) -> None:
        """Запомнить отрицаемую спецификацию."""
        self._inner = inner

    def is_satisfied_by(self, candidate: T) -> bool:
        """Инвертировать результат вложенной спецификации."""
        return not self._inner.is_satisfied_by(candidate)
