"""Домен Tenancy: value objects и агрегат ``Master``."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import uuid4

import pytest

from beauty.contexts.tenancy.domain.errors import (
    InvalidBookingRules,
    InvalidMasterSlug,
    InvalidMoney,
    InvalidProfile,
    InvalidServiceDuration,
    InvalidTimeZone,
    InvalidWeeklySchedule,
    MasterNotPublishable,
    ServiceLimitReached,
    UnknownService,
)
from beauty.contexts.tenancy.domain.events import (
    MasterPublished,
    MasterRegistered,
    MasterScheduleChanged,
    MasterServicesChanged,
)
from beauty.contexts.tenancy.domain.master import MAX_ACTIVE_SERVICES, Master, MasterProfile
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
    WorkingHours,
)
from tests.fakes import FrozenClock

NAMES = NameForms("Алиса", "Алисы", "Алисе")
WEEKDAYS = WeeklySchedule({d: (WorkingHours(time(10), time(19)),) for d in range(6)})


def new_master(clock: FrozenClock, slug: str = "alisa") -> Master:
    """Черновик мастера."""
    return Master.register(
        master_id=uuid4(),
        slug=MasterSlug(slug),
        display_name="Алиса Мельникова",
        name_forms=NAMES,
        timezone=TimeZoneName("Asia/Almaty"),
        now=clock.now(),
    )


def publishable(clock: FrozenClock) -> Master:
    """Мастер с услугой и расписанием."""
    master = new_master(clock)
    master.add_service(uuid4(), "Массаж спины", ServiceDuration(40), Money(900_000), clock.now())
    master.set_schedule(WEEKDAYS, clock.now())
    return master


class TestValueObjects:
    @pytest.mark.parametrize("slug", ["alisa", "a1", "dana-nails", "x" * 40])
    def test_valid_slugs(self, slug: str) -> None:
        assert MasterSlug(slug).value == slug

    @pytest.mark.parametrize(
        "slug", ["a", "Alisa", "-alisa", "alisa-", "али", "a_b", "x" * 41, "www", "master"]
    )
    def test_invalid_slugs(self, slug: str) -> None:
        with pytest.raises(InvalidMasterSlug):
            MasterSlug(slug)

    def test_timezone(self) -> None:
        assert TimeZoneName("Asia/Almaty").zone().key == "Asia/Almaty"
        with pytest.raises(InvalidTimeZone):
            TimeZoneName("Mars/Olympus")

    @pytest.mark.parametrize("minutes", [0, 3, 7, 485])
    def test_invalid_duration(self, minutes: int) -> None:
        with pytest.raises(InvalidServiceDuration):
            ServiceDuration(minutes)

    def test_money(self) -> None:
        assert Money(0).amount == 0
        with pytest.raises(InvalidMoney):
            Money(-1)
        with pytest.raises(InvalidMoney):
            Money(100, "USD")

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"confirm_within_hours": 0},
            {"change_deadline_hours": -1},
            {"horizon_days": 0},
            {"horizon_days": 91},
            {"slot_step_minutes": 25},
        ],
    )
    def test_invalid_booking_rules(self, kwargs: dict[str, int]) -> None:
        with pytest.raises(InvalidBookingRules):
            BookingRules(**kwargs)

    def test_schedule_normalized_and_overlaps_rejected(self) -> None:
        schedule = WeeklySchedule(
            {0: (WorkingHours(time(15), time(19)), WorkingHours(time(10), time(14))), 6: ()}
        )
        assert schedule.hours_on(0)[0].start == time(10)
        assert 6 not in schedule.days
        with pytest.raises(InvalidWeeklySchedule):
            WeeklySchedule({0: (WorkingHours(time(10), time(14)), WorkingHours(time(13), time(18)))})
        with pytest.raises(InvalidWeeklySchedule):
            WorkingHours(time(10, 7), time(12))
        with pytest.raises(InvalidWeeklySchedule):
            WorkingHours(time(12), time(12))
        with pytest.raises(InvalidWeeklySchedule):
            WeeklySchedule({7: (WorkingHours(time(10), time(12)),)})

    def test_name_forms_required(self) -> None:
        with pytest.raises(InvalidProfile):
            NameForms("Алиса", " ", "Алисе")

    def test_photo_requires_https(self) -> None:
        with pytest.raises(InvalidProfile):
            PortfolioPhoto(uuid4(), "http://example.com/1.jpg")


class TestMaster:
    def test_register_is_draft(self, clock: FrozenClock) -> None:
        master = new_master(clock)
        assert master.status is MasterStatus.DRAFT
        assert [type(e) for e in master.pull_events()] == [MasterRegistered]

    def test_publish_requires_service_and_schedule(self, clock: FrozenClock) -> None:
        master = new_master(clock)
        with pytest.raises(MasterNotPublishable):
            master.publish(clock.now())
        master.add_service(uuid4(), "Массаж", ServiceDuration(40), None, clock.now())
        with pytest.raises(MasterNotPublishable):
            master.publish(clock.now())
        master.set_schedule(WEEKDAYS, clock.now())
        master.publish(clock.now())
        assert master.is_published
        assert isinstance(master.pull_events()[-1], MasterPublished)
        master.publish(clock.now())
        assert master.pull_events() == []

    def test_published_master_keeps_one_service_and_hours(self, clock: FrozenClock) -> None:
        master = publishable(clock)
        master.publish(clock.now())
        only = master.active_services[0].id
        with pytest.raises(MasterNotPublishable):
            master.archive_service(only, clock.now())
        with pytest.raises(MasterNotPublishable):
            master.set_schedule(WeeklySchedule(), clock.now())
        master.unpublish(clock.now())
        master.archive_service(only, clock.now())
        assert master.active_services == []

    def test_services_order_update_archive(self, clock: FrozenClock) -> None:
        master = new_master(clock)
        first = master.add_service(uuid4(), "  Массаж  ", ServiceDuration(40), Money(1), clock.now())
        second = master.add_service(uuid4(), "Чистка", ServiceDuration(90), None, clock.now())
        assert first.title == "Массаж"
        assert [s.position for s in master.active_services] == [0, 1]
        assert first.description == ""
        master.update_service(
            second.id, "Чистка лица", ServiceDuration(60), Money(5), clock.now(), "  Ультразвук и уход. "
        )
        assert master.service(second.id).duration.minutes == 60
        assert master.service(second.id).description == "Ультразвук и уход."
        with pytest.raises(InvalidProfile):
            master.add_service(uuid4(), "Пилинг", ServiceDuration(30), None, clock.now(), "x" * 1001)
        master.archive_service(first.id, clock.now())
        assert [s.id for s in master.active_services] == [second.id]
        with pytest.raises(UnknownService):
            master.update_service(first.id, "x", ServiceDuration(40), None, clock.now())
        changes = [e.change for e in master.pull_events() if isinstance(e, MasterServicesChanged)]
        assert changes == ["added", "added", "updated", "archived"]

    def test_service_limit(self, clock: FrozenClock) -> None:
        master = new_master(clock)
        for i in range(MAX_ACTIVE_SERVICES):
            master.add_service(uuid4(), f"Услуга {i}", ServiceDuration(30), None, clock.now())
        with pytest.raises(ServiceLimitReached):
            master.add_service(uuid4(), "Лишняя", ServiceDuration(30), None, clock.now())

    def test_changes_touch_updated_at(self, clock: FrozenClock) -> None:
        master = new_master(clock)
        clock.advance(timedelta(minutes=5))
        master.add_service(uuid4(), "Массаж", ServiceDuration(40), None, clock.now())
        assert master.updated_at == clock.now()

    def test_days_off_drop_past_and_dedupe(self, clock: FrozenClock) -> None:
        master = new_master(clock)
        today = date(2026, 10, 15)
        master.set_days_off(
            [date(2026, 10, 1), date(2026, 10, 20), date(2026, 10, 18), date(2026, 10, 20)],
            today,
            clock.now(),
        )
        assert master.days_off == (date(2026, 10, 18), date(2026, 10, 20))
        assert isinstance(master.pull_events()[-1], MasterScheduleChanged)

    def test_update_profile_validates(self, clock: FrozenClock) -> None:
        master = new_master(clock)
        profile = MasterProfile(
            display_name="  Алиса М.  ",
            name_forms=NAMES,
            specialty="Косметолог",
            address="Астана",
            about="Опыт 8 лет",
            timezone=TimeZoneName("Asia/Almaty"),
        )
        master.update_profile(profile, clock.now())
        assert master.display_name == "Алиса М."
        with pytest.raises(InvalidProfile):
            master.update_profile(
                MasterProfile("", NAMES, "", "", "", TimeZoneName("Asia/Almaty")), clock.now()
            )
        with pytest.raises(InvalidProfile):
            master.update_profile(
                MasterProfile("Алиса", NAMES, "", "", "", TimeZoneName("Asia/Almaty"), "http://x"),
                clock.now(),
            )

    def test_registered_at_is_kept(self, clock: FrozenClock) -> None:
        master = new_master(clock)
        assert master.created_at == datetime(2026, 10, 15, 12, 0, tzinfo=clock.now().tzinfo)


def test_unchanged_settings_record_no_events(clock: FrozenClock) -> None:
    """Повтор тех же профиля, расписания и правил — без событий (идемпотентный сид)."""
    master = publishable(clock)
    profile = MasterProfile("Алиса Мельникова", NAMES, "", "", "", TimeZoneName("Asia/Almaty"))
    master.update_profile(profile, clock.now())
    master.pull_events()
    version_marker = master.updated_at
    clock.advance(timedelta(minutes=1))
    master.update_profile(profile, clock.now())
    master.set_schedule(WEEKDAYS, clock.now())
    master.set_booking_rules(BookingRules(), clock.now())
    assert master.pull_events() == []
    assert master.updated_at == version_marker
