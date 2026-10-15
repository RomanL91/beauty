"""Политики подтверждения входа (Strategy).

Выбор политики — конфигурация (``BEAUTY_AUTH__CONFIRMATION_POLICY``), а не ветвление
в обработчиках: обработчики работают с абстракцией и не знают, какая политика
активна.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime

from beauty.contexts.identity.application.dto import ClaimResult, ClaimStep
from beauty.contexts.identity.domain.auth_challenge import AuthChallenge, ChallengeStatus
from beauty.contexts.identity.domain.services import ConfirmationCodeGenerator
from beauty.contexts.identity.domain.value_objects import ConfirmationCode, TelegramUserId


class ChallengeConfirmationPolicy(ABC):
    """Как пользователь подтверждает, что вход начат им."""

    def __init__(self, generator: ConfirmationCodeGenerator) -> None:
        """Получить генератор кодов."""
        self._generator = generator

    def generate_code(self) -> ConfirmationCode:
        """Код для показа в браузере."""
        return self._generator.generate()

    def after_claim(
        self, challenge: AuthChallenge, telegram_user: TelegramUserId, now: datetime
    ) -> ClaimResult:
        """Определить следующий шаг после открытия deep link."""
        if challenge.status is ChallengeStatus.CONFIRMED:
            return ClaimResult(challenge.id, ClaimStep.ASK_CONTACT)
        return self._next_step(challenge, telegram_user, now)

    @abstractmethod
    def _next_step(
        self, challenge: AuthChallenge, telegram_user: TelegramUserId, now: datetime
    ) -> ClaimResult:
        """Шаг для challenge в состоянии ``CLAIMED``."""


class NumberMatchingConfirmation(ChallengeConfirmationPolicy):
    """Пользователь выбирает в боте код, совпадающий с кодом в браузере."""

    def _next_step(
        self, challenge: AuthChallenge, telegram_user: TelegramUserId, now: datetime
    ) -> ClaimResult:
        """Попросить выбрать код из вариантов."""
        options = self._generator.options_for(challenge.confirmation_code)
        return ClaimResult(challenge.id, ClaimStep.ASK_CODE, tuple(option.value for option in options))


class ImplicitConfirmation(ChallengeConfirmationPolicy):
    """Без сверки кода: сразу к контакту (только для разработки)."""

    def _next_step(
        self, challenge: AuthChallenge, telegram_user: TelegramUserId, now: datetime
    ) -> ClaimResult:
        """Подтвердить вход и попросить контакт."""
        challenge.confirm_implicitly(telegram_user, now)
        return ClaimResult(challenge.id, ClaimStep.ASK_CONTACT)


class ConfirmationPolicyFactory:
    """Создаёт политику по имени из конфигурации."""

    _POLICIES: Mapping[str, type[ChallengeConfirmationPolicy]] = {
        "number_matching": NumberMatchingConfirmation,
        "implicit": ImplicitConfirmation,
    }

    def create(self, name: str, generator: ConfirmationCodeGenerator) -> ChallengeConfirmationPolicy:
        """Вернуть политику; неизвестное имя — ошибка конфигурации."""
        try:
            return self._POLICIES[name](generator)
        except KeyError as error:
            raise ValueError(f"Неизвестная политика подтверждения: {name}") from error
