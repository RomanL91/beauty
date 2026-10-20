"""Прикладные ошибки Conversations."""

from __future__ import annotations

from beauty.shared.application.errors import ConflictError, NotFoundError


class ConversationNotFoundError(NotFoundError):
    """Переписка не найдена."""

    code = "conversation_not_found"


class MasterNotFoundError(NotFoundError):
    """Мастер не найден."""

    code = "master_not_found"


class ServiceNotFoundError(NotFoundError):
    """У мастера нет такой услуги."""

    code = "service_not_found"


class OfferNotFoundError(NotFoundError):
    """Предложение окон не найдено."""

    code = "offer_not_found"


class SlotNotAvailableError(ConflictError):
    """Окно недоступно для записи (занято или вне расписания)."""

    code = "slot_unavailable"


class BroadcastNotFoundError(NotFoundError):
    """Рассылка не найдена."""

    code = "broadcast_not_found"
