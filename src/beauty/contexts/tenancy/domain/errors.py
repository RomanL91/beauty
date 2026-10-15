"""Доменные ошибки контекста Tenancy."""

from __future__ import annotations

from beauty.shared.domain.errors import DomainError, InvariantViolation


class InvalidMasterSlug(DomainError):
    """Адрес страницы мастера не подходит (латиница, цифры и дефис, 2–40 символов)."""

    code = "invalid_slug"


class InvalidProfile(DomainError):
    """Поле профиля мастера заполнено некорректно."""

    code = "invalid_profile"


class InvalidTimeZone(DomainError):
    """Неизвестный часовой пояс."""

    code = "invalid_timezone"


class InvalidServiceDuration(DomainError):
    """Длительность услуги — от 5 до 480 минут, кратно 5."""

    code = "invalid_service_duration"


class InvalidMoney(DomainError):
    """Некорректная цена."""

    code = "invalid_money"


class InvalidBookingRules(DomainError):
    """Некорректные правила записи."""

    code = "invalid_booking_rules"


class InvalidWeeklySchedule(DomainError):
    """Некорректное недельное расписание."""

    code = "invalid_schedule"


class ServiceLimitReached(InvariantViolation):
    """У мастера слишком много услуг."""

    code = "service_limit_reached"


class UnknownService(DomainError):
    """У мастера нет такой услуги."""

    code = "service_not_found"


class MasterNotPublishable(InvariantViolation):
    """Страницу нельзя опубликовать: нужны хотя бы одна услуга и рабочие часы."""

    code = "master_not_publishable"
