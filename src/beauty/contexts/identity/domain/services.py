"""Доменные сервисы контекста Identity."""

from __future__ import annotations

import random

from beauty.contexts.identity.domain.value_objects import ConfirmationCode


class ConfirmationCodeGenerator:
    """Генерирует код сверки и варианты-«приманки» для number matching.

    Источник случайности — ``SystemRandom`` (CSPRNG ОС); в тестах передаётся
    детерминированный ``random.Random``.
    """

    def __init__(self, randomness: random.Random | None = None, options_count: int = 3) -> None:
        """Задать источник случайности и число вариантов в боте."""
        if options_count < 2:
            raise ValueError("Нужно минимум два варианта, иначе сверка бессмысленна")
        self._random = randomness or random.SystemRandom()
        self._options_count = options_count

    def generate(self) -> ConfirmationCode:
        """Новый двузначный код."""
        return ConfirmationCode(f"{self._random.randrange(10, 100):02d}")

    def options_for(self, code: ConfirmationCode) -> tuple[ConfirmationCode, ...]:
        """Перемешанные варианты, среди которых ровно один верный."""
        decoys: set[str] = set()
        while len(decoys) < self._options_count - 1:
            candidate = f"{self._random.randrange(10, 100):02d}"
            if candidate != code.value:
                decoys.add(candidate)
        options = [code, *(ConfirmationCode(value) for value in sorted(decoys))]
        self._random.shuffle(options)
        return tuple(options)
