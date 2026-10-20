"""Read-модели Tenancy (SQL → DTO без агрегатов).

Публичная страница и поиск окон — самые частые запросы платформы (их дёргает
каждый посетитель страницы мастера), поэтому они не грузят агрегат с трекингом,
а читают нужные колонки двумя лёгкими запросами по уникальному ``slug`` и
частичному индексу активных услуг.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.tenancy.application.dto import MasterPageView, PhotoView, ServiceView
from beauty.contexts.tenancy.application.ports import (
    AvailabilityReader,
    AvailabilityRecord,
    BookableService,
    MasterDirectory,
    MasterPageReader,
    MasterRef,
)
from beauty.contexts.tenancy.domain.errors import InvalidMasterSlug
from beauty.contexts.tenancy.domain.slots import Availability
from beauty.contexts.tenancy.domain.value_objects import BookingRules, MasterSlug, MasterStatus
from beauty.contexts.tenancy.infrastructure.tables import master_services, masters


def _slug(raw: str) -> MasterSlug | None:
    """Некорректный адрес — просто «не найдено», без запроса в БД."""
    try:
        return MasterSlug(raw)
    except InvalidMasterSlug:
        return None


def _published(master: MasterRef, *, published_only: bool = True) -> ColumnElement[bool] | None:
    """Условие «(опубликованный) мастер с этим slug или id»; ``None`` — заведомо не найдётся."""
    if isinstance(master, UUID):
        key: ColumnElement[bool] = masters.c.id == master
    else:
        valid = _slug(master)
        if valid is None:
            return None
        key = masters.c.slug == valid
    return key & (masters.c.status == MasterStatus.PUBLISHED) if published_only else key


class _Reader:
    """Общее: фабрика сессий и выборка активных услуг."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Получить фабрику сессий."""
        self._session_factory = session_factory

    @staticmethod
    async def _active_services(session: AsyncSession, master_id: UUID) -> Sequence[Any]:
        statement = (
            select(
                master_services.c.id,
                master_services.c.title,
                master_services.c.duration_min,
                master_services.c.price_amount,
                master_services.c.description,
            )
            .where(master_services.c.master_id == master_id, master_services.c.archived_at.is_(None))
            .order_by(master_services.c.position)
        )
        return (await session.execute(statement)).all()


class SqlMasterPageReader(_Reader, MasterPageReader):
    """Страница опубликованного мастера."""

    async def read(self, master: MasterRef, *, published_only: bool = True) -> MasterPageView | None:
        """Профиль, активные услуги, фото и правила."""
        condition = _published(master, published_only=published_only)
        if condition is None:
            return None
        statement = select(masters).where(condition)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                return None
            services = await self._active_services(session, row.id)
        return MasterPageView(
            id=row.id,
            slug=row.slug.value,
            display_name=row.display_name,
            name_nominative=row.name_nominative,
            name_genitive=row.name_genitive,
            name_dative=row.name_dative,
            specialty=row.specialty,
            address=row.address,
            timezone=row.timezone.value,
            avatar_url=row.avatar_url,
            about=row.about,
            services=tuple(
                ServiceView(
                    id=s.id,
                    title=s.title,
                    duration_min=s.duration_min.minutes,
                    price_amount=None if s.price_amount is None else s.price_amount.amount,
                    description=s.description,
                )
                for s in services
            ),
            photos=tuple(PhotoView(p.id, p.url, p.alt) for p in row.photos),
            confirm_within_hours=row.confirm_within_hours,
            change_deadline_hours=row.change_deadline_hours,
        )


class SqlAvailabilityReader(_Reader, AvailabilityReader):
    """Снимок доступности опубликованного мастера."""

    async def read(self, master: MasterRef, *, published_only: bool = True) -> AvailabilityRecord | None:
        """Пояс, расписание, выходные, правила и длительности услуг."""
        condition = _published(master, published_only=published_only)
        if condition is None:
            return None
        statement = select(
            masters.c.id,
            masters.c.timezone,
            masters.c.schedule,
            masters.c.days_off,
            masters.c.confirm_within_hours,
            masters.c.change_deadline_hours,
            masters.c.min_notice_minutes,
            masters.c.horizon_days,
            masters.c.slot_step_minutes,
        ).where(condition)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                return None
            services = await self._active_services(session, row.id)
        return AvailabilityRecord(
            master_id=row.id,
            availability=Availability(
                timezone=row.timezone.zone(),
                schedule=row.schedule,
                days_off=frozenset(row.days_off),
                rules=BookingRules(
                    confirm_within_hours=row.confirm_within_hours,
                    change_deadline_hours=row.change_deadline_hours,
                    min_notice_minutes=row.min_notice_minutes,
                    horizon_days=row.horizon_days,
                    slot_step_minutes=row.slot_step_minutes,
                ),
            ),
            services=tuple(BookableService(s.id, s.duration_min.minutes) for s in services),
        )


class SqlMasterDirectory(_Reader, MasterDirectory):
    """Каталог мастеров для администрирования (видит и черновики)."""

    async def find_id(self, slug: str) -> UUID | None:
        """Id мастера по адресу."""
        valid = _slug(slug)
        if valid is None:
            return None
        async with self._session_factory() as session:
            found: UUID | None = (
                await session.execute(select(masters.c.id).where(masters.c.slug == valid))
            ).scalar_one_or_none()
        return found

    async def find_by_owner(self, phone: str) -> UUID | None:
        """Id мастера по телефону владельца."""
        async with self._session_factory() as session:
            found: UUID | None = (
                await session.execute(select(masters.c.id).where(masters.c.owner_phone == phone))
            ).scalar_one_or_none()
        return found

    async def active_service_titles(self, master_id: UUID) -> frozenset[str]:
        """Названия активных услуг."""
        async with self._session_factory() as session:
            rows = await self._active_services(session, master_id)
        return frozenset(row.title for row in rows)
