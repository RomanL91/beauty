"""Доменный слой shared kernel.

Не зависит ни от SQLAlchemy, ни от брокера, ни от веб-фреймворка: только стандартная
библиотека. Всё, что здесь определено, контексты используют как базовые блоки.
"""

from beauty.shared.domain.aggregate import AggregateRoot, Entity
from beauty.shared.domain.clock import Clock, SystemClock
from beauty.shared.domain.errors import DomainError, InvariantViolation
from beauty.shared.domain.events import DomainEvent
from beauty.shared.domain.ids import IdGenerator, UuidV7Generator, default_id_generator
from beauty.shared.domain.secrets import HashedSecret
from beauty.shared.domain.specification import Specification

__all__ = [
    "AggregateRoot",
    "Clock",
    "DomainError",
    "DomainEvent",
    "Entity",
    "HashedSecret",
    "IdGenerator",
    "InvariantViolation",
    "Specification",
    "SystemClock",
    "UuidV7Generator",
    "default_id_generator",
]
