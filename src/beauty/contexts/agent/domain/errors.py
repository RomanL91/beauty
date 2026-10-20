"""Доменные ошибки контекста Agent."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError, InvariantViolation


class InvalidTicket(DomainError):
    """Тикет запуска неизвестен, чужой или истёк."""

    code = "invalid_ticket"


class ChoiceAlreadyAnswered(InvariantViolation):
    """На этот вопрос мастер уже выбрал другой вариант."""

    code = "choice_already_answered"


class UnknownChoiceOption(DomainError):
    """Такого вопроса или варианта нет."""

    code = "choice_not_found"


class InvalidPractice(DomainError):
    """Запись опыта — от 1 до 500 символов."""

    code = "invalid_practice"


class PracticesLimit(DomainError):
    """У мастера уже 200 записей опыта — удалите устаревшие."""

    code = "practices_limit"


class UnknownPractice(DomainError):
    """Запись опыта не найдена."""

    code = "practice_not_found"
