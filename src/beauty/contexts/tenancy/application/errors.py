"""Прикладные ошибки Tenancy."""

from __future__ import annotations

from beauty.shared.application.errors import ApplicationError, ConflictError, NotFoundError


class MasterNotFoundError(NotFoundError):
    """Мастер не найден (или его страница не опубликована)."""

    code = "master_not_found"


class ServiceNotFoundError(NotFoundError):
    """У мастера нет такой услуги."""

    code = "service_not_found"


class SlugTakenError(ConflictError):
    """Адрес страницы уже занят."""

    code = "slug_taken"


class OwnerTakenError(ConflictError):
    """Этот телефон уже владеет другой страницей мастера."""

    code = "owner_taken"


class InvalidSlotWindowError(ApplicationError):
    """Некорректные границы поиска окон."""

    code = "invalid_slot_window"


class SlotUnavailableError(ConflictError):
    """Это время недоступно для записи (занято, вне расписания или правил)."""

    code = "slot_unavailable"


class PhotoNotFoundError(ApplicationError):
    """Фото работы не найдено."""

    code = "photo_not_found"
