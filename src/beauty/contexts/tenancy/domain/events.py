"""Доменные события контекста Tenancy.

Поля — примитивы: события читают другие контексты (запись, агент), и контракт не
должен зависеть от внутренних value objects Tenancy.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beauty.shared.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class MasterRegistered(DomainEvent):
    """Мастер зарегистрирован (страница — черновик)."""

    routing_key = "tenancy.master.registered"

    master_id: UUID
    slug: str


@dataclass(frozen=True, kw_only=True)
class MasterProfileChanged(DomainEvent):
    """Изменился профиль (имя, описание, часовой пояс, фото)."""

    routing_key = "tenancy.master.profile_changed"

    master_id: UUID


@dataclass(frozen=True, kw_only=True)
class MasterServicesChanged(DomainEvent):
    """Изменился состав или параметры услуг."""

    routing_key = "tenancy.master.services_changed"

    master_id: UUID
    service_id: UUID
    change: str


@dataclass(frozen=True, kw_only=True)
class MasterScheduleChanged(DomainEvent):
    """Изменились рабочие часы, выходные или правила записи."""

    routing_key = "tenancy.master.schedule_changed"

    master_id: UUID


@dataclass(frozen=True, kw_only=True)
class MasterPublished(DomainEvent):
    """Страница мастера открыта для клиентов."""

    routing_key = "tenancy.master.published"

    master_id: UUID
    slug: str


@dataclass(frozen=True, kw_only=True)
class MasterUnpublished(DomainEvent):
    """Страница мастера скрыта."""

    routing_key = "tenancy.master.unpublished"

    master_id: UUID
    slug: str
