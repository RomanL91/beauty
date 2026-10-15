"""Агрегат ``Master`` — мастер-арендатор платформы и его публичная страница.

Услуги — сущности внутри агрегата: их число, порядок и правило «у опубликованной
страницы есть хотя бы одна услуга» проверяются в одной транзакции с мастером.
Любое изменение услуг трогает ``updated_at`` мастера — так растёт ``version`` и
параллельные правки одного мастера ловятся оптимистичной блокировкой.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from beauty.contexts.tenancy.domain.errors import (
    InvalidProfile,
    MasterNotPublishable,
    ServiceLimitReached,
    UnknownService,
)
from beauty.contexts.tenancy.domain.events import (
    MasterProfileChanged,
    MasterPublished,
    MasterRegistered,
    MasterScheduleChanged,
    MasterServicesChanged,
    MasterUnpublished,
)
from beauty.contexts.tenancy.domain.value_objects import (
    BookingRules,
    MasterSlug,
    MasterStatus,
    Money,
    NameForms,
    PortfolioPhoto,
    ServiceDuration,
    TimeZoneName,
    WeeklySchedule,
)
from beauty.shared.domain.aggregate import AggregateRoot, Entity
from beauty.shared.domain.events import DomainEvent

MAX_ACTIVE_SERVICES = 50
MAX_PHOTOS = 30
MAX_DAYS_OFF = 366


def _text(value: str, *, field: str, max_length: int, required: bool = False) -> str:
    """Обрезать пробелы и проверить длину текстового поля."""
    cleaned = value.strip()
    if required and not cleaned:
        raise InvalidProfile(f"Поле «{field}» обязательно")
    if len(cleaned) > max_length:
        raise InvalidProfile(f"Поле «{field}» — не длиннее {max_length} символов")
    return cleaned


@dataclass(frozen=True, slots=True)
class MasterProfile:
    """Профиль страницы мастера (для команды обновления)."""

    display_name: str
    name_forms: NameForms
    specialty: str
    address: str
    about: str
    timezone: TimeZoneName
    avatar_url: str | None = None


class Service(Entity):
    """Услуга мастера."""

    def __init__(
        self, service_id: UUID, title: str, duration: ServiceDuration, price: Money | None, position: int
    ) -> None:
        """Создать услугу (только через ``Master.add_service``)."""
        self.id = service_id
        self.title = _text(title, field="название услуги", max_length=120, required=True)
        self.duration = duration
        self.price = price
        self.position = position
        self.archived_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Услуга доступна для записи."""
        return self.archived_at is None


class Master(AggregateRoot):
    """Мастер и его страница."""

    def __init__(
        self,
        master_id: UUID,
        slug: MasterSlug,
        display_name: str,
        name_forms: NameForms,
        timezone: TimeZoneName,
        created_at: datetime,
    ) -> None:
        """Создать мастера (используйте ``register``)."""
        self.id = master_id
        self.slug = slug
        self.status = MasterStatus.DRAFT
        self.display_name = _text(display_name, field="имя", max_length=80, required=True)
        self.name_forms = name_forms
        self.specialty = ""
        self.address = ""
        self.about = ""
        self.avatar_url: str | None = None
        self.timezone = timezone
        self.booking_rules = BookingRules()
        self.schedule = WeeklySchedule()
        self.days_off: tuple[date, ...] = ()
        self.photos: tuple[PortfolioPhoto, ...] = ()
        self.services: list[Service] = []
        self.created_at = created_at
        self.updated_at = created_at
        self.published_at: datetime | None = None

    @classmethod
    def register(
        cls,
        *,
        master_id: UUID,
        slug: MasterSlug,
        display_name: str,
        name_forms: NameForms,
        timezone: TimeZoneName,
        now: datetime,
    ) -> Master:
        """Зарегистрировать мастера: страница — черновик без услуг и расписания."""
        master = cls(master_id, slug, display_name, name_forms, timezone, now)
        master._record(MasterRegistered(occurred_at=now, master_id=master_id, slug=slug.value))
        return master

    # ─────────────────────────── профиль ───────────────────────────

    def update_profile(self, profile: MasterProfile, now: datetime) -> None:
        """Обновить профиль страницы."""
        if profile.avatar_url is not None and not profile.avatar_url.startswith("https://"):
            raise InvalidProfile("Фото профиля — https-ссылка")
        normalized = MasterProfile(
            display_name=_text(profile.display_name, field="имя", max_length=80, required=True),
            name_forms=profile.name_forms,
            specialty=_text(profile.specialty, field="специализация", max_length=80),
            address=_text(profile.address, field="адрес", max_length=200),
            about=_text(profile.about, field="о мастере", max_length=4000),
            timezone=profile.timezone,
            avatar_url=profile.avatar_url,
        )
        if normalized == self.profile:
            return
        self.display_name = normalized.display_name
        self.name_forms = normalized.name_forms
        self.specialty = normalized.specialty
        self.address = normalized.address
        self.about = normalized.about
        self.timezone = normalized.timezone
        self.avatar_url = normalized.avatar_url
        self._touch(now, MasterProfileChanged(occurred_at=now, master_id=self.id))

    @property
    def profile(self) -> MasterProfile:
        """Текущий профиль."""
        return MasterProfile(
            display_name=self.display_name,
            name_forms=self.name_forms,
            specialty=self.specialty,
            address=self.address,
            about=self.about,
            timezone=self.timezone,
            avatar_url=self.avatar_url,
        )

    def replace_photos(self, photos: Iterable[PortfolioPhoto], now: datetime) -> None:
        """Заменить подборку фото работ."""
        photos = tuple(photos)
        if len(photos) > MAX_PHOTOS:
            raise InvalidProfile(f"Не больше {MAX_PHOTOS} фото")
        if len({p.id for p in photos}) != len(photos):
            raise InvalidProfile("Повторяющиеся фото")
        self.photos = photos
        self._touch(now, MasterProfileChanged(occurred_at=now, master_id=self.id))

    # ─────────────────────────── услуги ───────────────────────────

    @property
    def active_services(self) -> list[Service]:
        """Активные услуги в порядке показа."""
        return sorted((s for s in self.services if s.is_active), key=lambda s: s.position)

    def add_service(
        self, service_id: UUID, title: str, duration: ServiceDuration, price: Money | None, now: datetime
    ) -> Service:
        """Добавить услугу в конец списка."""
        if len(self.active_services) >= MAX_ACTIVE_SERVICES:
            raise ServiceLimitReached(f"Не больше {MAX_ACTIVE_SERVICES} услуг")
        position = max((s.position for s in self.services), default=-1) + 1
        service = Service(service_id, title, duration, price, position)
        self.services.append(service)
        self._touch(
            now,
            MasterServicesChanged(occurred_at=now, master_id=self.id, service_id=service_id, change="added"),
        )
        return service

    def update_service(
        self, service_id: UUID, title: str, duration: ServiceDuration, price: Money | None, now: datetime
    ) -> None:
        """Изменить название, длительность или цену."""
        service = self._active_service(service_id)
        service.title = _text(title, field="название услуги", max_length=120, required=True)
        service.duration = duration
        service.price = price
        self._touch(
            now,
            MasterServicesChanged(
                occurred_at=now, master_id=self.id, service_id=service_id, change="updated"
            ),
        )

    def archive_service(self, service_id: UUID, now: datetime) -> None:
        """Убрать услугу из записи (история записей на неё сохраняется)."""
        service = self._active_service(service_id)
        if self.status is MasterStatus.PUBLISHED and len(self.active_services) == 1:
            raise MasterNotPublishable("У опубликованной страницы должна остаться хотя бы одна услуга")
        service.archived_at = now
        self._touch(
            now,
            MasterServicesChanged(
                occurred_at=now, master_id=self.id, service_id=service_id, change="archived"
            ),
        )

    def service(self, service_id: UUID) -> Service:
        """Активная услуга по id."""
        return self._active_service(service_id)

    def _active_service(self, service_id: UUID) -> Service:
        for service in self.services:
            if service.id == service_id and service.is_active:
                return service
        raise UnknownService(f"Услуга {service_id} не найдена")

    # ─────────────────────── расписание и правила ───────────────────────

    def set_schedule(self, schedule: WeeklySchedule, now: datetime) -> None:
        """Заменить недельное расписание."""
        if self.status is MasterStatus.PUBLISHED and schedule.is_empty:
            raise MasterNotPublishable("У опубликованной страницы должны быть рабочие часы")
        if schedule == self.schedule:
            return
        self.schedule = schedule
        self._touch(now, MasterScheduleChanged(occurred_at=now, master_id=self.id))

    def set_booking_rules(self, rules: BookingRules, now: datetime) -> None:
        """Заменить правила записи."""
        if rules == self.booking_rules:
            return
        self.booking_rules = rules
        self._touch(now, MasterScheduleChanged(occurred_at=now, master_id=self.id))

    def set_days_off(self, days: Iterable[date], today: date, now: datetime) -> None:
        """Задать выходные даты; прошедшие отбрасываются.

        ``today`` — локальная дата мастера (её считает приложение по его поясу).
        """
        upcoming = tuple(sorted({d for d in days if d >= today}))
        if len(upcoming) > MAX_DAYS_OFF:
            raise InvalidProfile(f"Не больше {MAX_DAYS_OFF} выходных дат")
        self.days_off = upcoming
        self._touch(now, MasterScheduleChanged(occurred_at=now, master_id=self.id))

    # ─────────────────────────── публикация ───────────────────────────

    @property
    def is_published(self) -> bool:
        """Страница видна клиентам."""
        return self.status is MasterStatus.PUBLISHED

    def publish(self, now: datetime) -> None:
        """Открыть страницу клиентам."""
        if self.is_published:
            return
        if not self.active_services:
            raise MasterNotPublishable("Добавьте хотя бы одну услугу")
        if self.schedule.is_empty:
            raise MasterNotPublishable("Задайте рабочие часы")
        self.status = MasterStatus.PUBLISHED
        self.published_at = now
        self._touch(now, MasterPublished(occurred_at=now, master_id=self.id, slug=self.slug.value))

    def unpublish(self, now: datetime) -> None:
        """Скрыть страницу."""
        if not self.is_published:
            return
        self.status = MasterStatus.DRAFT
        self._touch(now, MasterUnpublished(occurred_at=now, master_id=self.id, slug=self.slug.value))

    def _touch(self, now: datetime, event: DomainEvent) -> None:
        """Отметить изменение агрегата (растёт ``version``) и записать событие."""
        self.updated_at = now
        self._record(event)
