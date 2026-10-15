"""Прикладной слой shared kernel.

Определяет CQRS-абстракции (команды, запросы, обработчики, медиатор с конвейером
middleware), контракт Unit of Work, прикладные ошибки и порты инфраструктуры,
общие для всех контекстов.
"""

from beauty.shared.application.cqrs import Command, Handler, Query, Request
from beauty.shared.application.errors import (
    AccessDeniedError,
    ApplicationError,
    ConcurrencyConflictError,
    ConflictError,
    NotFoundError,
)
from beauty.shared.application.mediator import Mediator
from beauty.shared.application.uow import UnitOfWork

__all__ = [
    "AccessDeniedError",
    "ApplicationError",
    "Command",
    "ConcurrencyConflictError",
    "ConflictError",
    "Handler",
    "Mediator",
    "NotFoundError",
    "Query",
    "Request",
    "UnitOfWork",
]
