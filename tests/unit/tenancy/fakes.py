"""In-memory двойники Tenancy: репозиторий, Unit of Work, read-модели."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from beauty.contexts.tenancy.application.dto import MasterPageView, PhotoView, ServiceView
from beauty.contexts.tenancy.application.ports import (
    AvailabilityReader,
    AvailabilityRecord,
    BookableService,
    BusyTimeSource,
    MasterDirectory,
    MasterPageReader,
    MasterRef,
)
from beauty.contexts.tenancy.application.uow import TenancyUnitOfWork
from beauty.contexts.tenancy.domain.master import Master
from beauty.contexts.tenancy.domain.repositories import MasterRepository
from beauty.contexts.tenancy.domain.slots import Availability, TimeInterval
from beauty.contexts.tenancy.domain.value_objects import MasterSlug
from beauty.shared.domain.events import DomainEvent
from beauty.shared.infrastructure.db.tracker import AggregateTracker


class TenancyStore:
    """Хранилище, переживающее Unit of Work."""

    def __init__(self) -> None:
        """Пусто."""
        self.masters: dict[UUID, Master] = {}
        self.events: list[DomainEvent] = []
        self.commits = 0


class InMemoryMasters(MasterRepository):
    """Мастера в памяти."""

    def __init__(self, store: TenancyStore, tracker: AggregateTracker) -> None:
        """Связать с хранилищем."""
        self._store, self._tracker = store, tracker

    def add(self, master: Master) -> None:
        """Добавить."""
        self._store.masters[master.id] = self._tracker.track(master)

    async def get(self, master_id: UUID) -> Master | None:
        """По id."""
        found = self._store.masters.get(master_id)
        return None if found is None else self._tracker.track(found)

    async def get_by_owner(self, phone: str) -> Master | None:
        """По телефону владельца."""
        for master in self._store.masters.values():
            if master.owner_phone == phone:
                return self._tracker.track(master)
        return None

    async def get_by_slug(self, slug: MasterSlug) -> Master | None:
        """По slug."""
        for master in self._store.masters.values():
            if master.slug == slug:
                return self._tracker.track(master)
        return None


class InMemoryTenancyUnitOfWork(TenancyUnitOfWork):
    """Unit of Work: коммит собирает события; без коммита — «откат» не нужен (тесты)."""

    def __init__(self, store: TenancyStore) -> None:
        """Связать с хранилищем."""
        self._store = store
        self._tracker = AggregateTracker()

    async def _begin(self) -> None:
        self._tracker = AggregateTracker()
        self.masters = InMemoryMasters(self._store, self._tracker)

    async def commit(self) -> None:
        """Сохранить события."""
        self._store.events.extend(self._tracker.collect_events())
        self._store.commits += 1

    async def rollback(self) -> None:
        """Нечего откатывать."""


class StoreReaders(MasterPageReader, AvailabilityReader, MasterDirectory):
    """Read-модели поверх того же хранилища (как SQL-читатели поверх таблиц)."""

    def __init__(self, store: TenancyStore) -> None:
        """Связать с хранилищем."""
        self._store = store

    def _published(self, ref: MasterRef, published_only: bool = True) -> Master | None:
        for master in self._store.masters.values():
            if ref in (master.id, master.slug.value) and (master.is_published or not published_only):
                return master
        return None

    async def read(  # type: ignore[override]
        self, master_ref: MasterRef, *, published_only: bool = True
    ) -> MasterPageView | None:
        """Страница (для MasterPageReader)."""
        master = self._published(master_ref, published_only)
        if master is None:
            return None
        return MasterPageView(
            id=master.id,
            slug=master.slug.value,
            display_name=master.display_name,
            name_nominative=master.name_forms.nominative,
            name_genitive=master.name_forms.genitive,
            name_dative=master.name_forms.dative,
            specialty=master.specialty,
            address=master.address,
            timezone=master.timezone.value,
            avatar_url=master.avatar_url,
            about=master.about,
            services=tuple(
                ServiceView(
                    s.id,
                    s.title,
                    s.duration.minutes,
                    None if s.price is None else s.price.amount,
                    s.description,
                )
                for s in master.active_services
            ),
            photos=tuple(PhotoView(p.id, p.url, p.alt) for p in master.photos),
            confirm_within_hours=master.booking_rules.confirm_within_hours,
            change_deadline_hours=master.booking_rules.change_deadline_hours,
        )

    async def availability(
        self, master_ref: MasterRef, published_only: bool = True
    ) -> AvailabilityRecord | None:
        """Снимок доступности."""
        master = self._published(master_ref, published_only)
        if master is None:
            return None
        return AvailabilityRecord(
            master_id=master.id,
            availability=Availability(
                timezone=master.timezone.zone(),
                schedule=master.schedule,
                days_off=frozenset(master.days_off),
                rules=master.booking_rules,
            ),
            services=tuple(BookableService(s.id, s.duration.minutes) for s in master.active_services),
        )

    async def find_id(self, slug: str) -> UUID | None:
        """Id по slug."""
        for master in self._store.masters.values():
            if master.slug.value == slug:
                return master.id
        return None

    async def find_by_owner(self, phone: str) -> UUID | None:
        """Id по телефону владельца."""
        return next((m.id for m in self._store.masters.values() if m.owner_phone == phone), None)

    async def active_service_titles(self, master_id: UUID) -> frozenset[str]:
        """Названия активных услуг."""
        return frozenset(s.title for s in self._store.masters[master_id].active_services)

    async def removed_service_titles(self, master_id: UUID, since: datetime) -> tuple[str, ...]:
        """Убранные с ``since``, кроме вернувшихся названий; свежие первыми."""
        master = self._store.masters[master_id]
        active = {s.title.casefold() for s in master.active_services}
        removed = sorted(
            (s for s in master.services if s.archived_at is not None and s.archived_at >= since),
            key=lambda s: s.archived_at or since,
            reverse=True,
        )
        return tuple(dict.fromkeys(s.title for s in removed if s.title.casefold() not in active))


class AvailabilityAdapter(AvailabilityReader):
    """``AvailabilityReader`` над ``StoreReaders`` (у портов одинаковое имя метода)."""

    def __init__(self, readers: StoreReaders) -> None:
        """Обернуть читателей."""
        self._readers = readers

    async def read(self, master: MasterRef, *, published_only: bool = True) -> AvailabilityRecord | None:
        """Снимок."""
        return await self._readers.availability(master, published_only)


class FixedBusy(BusyTimeSource):
    """Заданное занятое время; запоминает запрошенное окно."""

    def __init__(self, intervals: list[TimeInterval] | None = None) -> None:
        """Интервалы занятости."""
        self.intervals = intervals or []
        self.requested: tuple[UUID, datetime, datetime] | None = None

    async def busy(self, master_id: UUID, start: datetime, end: datetime) -> list[TimeInterval]:
        """Вернуть интервалы."""
        self.requested = (master_id, start, end)
        return self.intervals
