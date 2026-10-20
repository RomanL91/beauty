"""Прикладной слой Tenancy: команды и запросы на in-memory двойниках."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from beauty.contexts.tenancy.application.commands import (
    AddService,
    AddServiceHandler,
    ArchiveService,
    ArchiveServiceHandler,
    AssignOwner,
    AssignOwnerHandler,
    PublishMaster,
    PublishMasterHandler,
    RegisterMaster,
    RegisterMasterHandler,
    ReplacePortfolio,
    ReplacePortfolioHandler,
    SetDaysOff,
    SetDaysOffHandler,
    SetWeeklySchedule,
    SetWeeklyScheduleHandler,
    UpdateService,
    UpdateServiceHandler,
)
from beauty.contexts.tenancy.application.errors import (
    InvalidSlotWindowError,
    MasterNotFoundError,
    OwnerTakenError,
    ServiceNotFoundError,
    SlugTakenError,
)
from beauty.contexts.tenancy.application.queries import (
    FindMasterByOwner,
    FindMasterByOwnerHandler,
    GetMasterPage,
    GetMasterPageHandler,
    ListFreeSlots,
    ListFreeSlotsHandler,
    ListRemovedServices,
    ListRemovedServicesHandler,
)
from beauty.contexts.tenancy.domain.errors import InvalidMasterSlug, InvalidProfile
from beauty.contexts.tenancy.domain.events import MasterPublished, MasterRegistered
from beauty.contexts.tenancy.domain.slots import SlotFinder, TimeInterval
from beauty.shared.domain.ids import UuidV7Generator
from tests.fakes import FrozenClock
from tests.unit.tenancy.fakes import (
    AvailabilityAdapter,
    FixedBusy,
    InMemoryTenancyUnitOfWork,
    StoreReaders,
    TenancyStore,
)

ALMATY_DAY = ((time(10), time(15)), (time(15, 30), time(19)))


class World:
    """Хранилище, часы и фабрики обработчиков."""

    def __init__(self, clock: FrozenClock) -> None:
        """Пустой мир."""
        self.store = TenancyStore()
        self.clock = clock
        self.ids = UuidV7Generator()
        self.readers = StoreReaders(self.store)
        self.busy = FixedBusy()

    def uow(self) -> InMemoryTenancyUnitOfWork:
        """Новый Unit of Work."""
        return InMemoryTenancyUnitOfWork(self.store)

    async def published_master(self) -> tuple[UUID, UUID, UUID]:
        """Мастер с двумя услугами (40 и 90 мин), Пн–Сб, опубликован."""
        master_id = await RegisterMasterHandler(self.uow(), self.clock, self.ids).handle(
            RegisterMaster("alisa", "Алиса Мельникова", "Алиса", "Алисы", "Алисе")
        )
        short = await AddServiceHandler(self.uow(), self.clock, self.ids).handle(
            AddService(master_id, "Массаж спины", 40, 900_000)
        )
        long = await AddServiceHandler(self.uow(), self.clock, self.ids).handle(
            AddService(master_id, "Чистка лица", 90, None)
        )
        await SetWeeklyScheduleHandler(self.uow(), self.clock).handle(
            SetWeeklySchedule(master_id, dict.fromkeys(range(6), ALMATY_DAY))
        )
        await PublishMasterHandler(self.uow(), self.clock).handle(PublishMaster(master_id))
        return master_id, short, long

    def slots(self) -> ListFreeSlotsHandler:
        """Обработчик поиска окон."""
        return ListFreeSlotsHandler(AvailabilityAdapter(self.readers), self.busy, SlotFinder(), self.clock)


@pytest.fixture
def world(clock: FrozenClock) -> World:
    """Чт 15 окт 2026, 12:00 UTC = 17:00 в Алматы."""
    return World(clock)


async def test_register_publish_and_page(world: World) -> None:
    master_id, _, _ = await world.published_master()
    kinds = [type(e) for e in world.store.events]
    assert kinds[0] is MasterRegistered
    assert kinds[-1] is MasterPublished

    page = await GetMasterPageHandler(world.readers).handle(GetMasterPage("alisa"))
    assert page.id == master_id
    assert [s.title for s in page.services] == ["Массаж спины", "Чистка лица"]
    assert page.services[0].price_amount == 900_000
    assert page.name_dative == "Алисе"


async def test_slug_taken_and_invalid(world: World) -> None:
    await world.published_master()
    handler = RegisterMasterHandler(world.uow(), world.clock, world.ids)
    with pytest.raises(SlugTakenError):
        await handler.handle(RegisterMaster("alisa", "Другая", "А", "Б", "В"))
    with pytest.raises(InvalidMasterSlug):
        await handler.handle(RegisterMaster("Alisa!", "Другая", "А", "Б", "В"))


async def test_draft_is_not_visible(world: World, clock: FrozenClock) -> None:
    await RegisterMasterHandler(world.uow(), clock, world.ids).handle(
        RegisterMaster("dana", "Дана", "Дана", "Даны", "Дане")
    )
    with pytest.raises(MasterNotFoundError):
        await GetMasterPageHandler(world.readers).handle(GetMasterPage("dana"))
    with pytest.raises(MasterNotFoundError):
        await world.slots().handle(ListFreeSlots("dana"))


async def test_service_commands(world: World) -> None:
    master_id, short, long = await world.published_master()
    await UpdateServiceHandler(world.uow(), world.clock).handle(
        UpdateService(master_id, long, "Чистка", 60, 100)
    )
    await ArchiveServiceHandler(world.uow(), world.clock).handle(ArchiveService(master_id, short))
    page = await GetMasterPageHandler(world.readers).handle(GetMasterPage("alisa"))
    assert [(s.title, s.duration_min) for s in page.services] == [("Чистка", 60)]
    with pytest.raises(ServiceNotFoundError):
        await ArchiveServiceHandler(world.uow(), world.clock).handle(ArchiveService(master_id, short))
    with pytest.raises(MasterNotFoundError):
        await AddServiceHandler(world.uow(), world.clock, world.ids).handle(
            AddService(uuid4(), "x", 30, None)
        )


async def test_removed_services_for_agent(world: World) -> None:
    """Убранные за 30 дней — агенту; вернувшееся название и старые — не в счёт."""
    master_id, short, long = await world.published_master()
    removed = ListRemovedServicesHandler(world.readers, world.clock)
    await AddServiceHandler(world.uow(), world.clock, world.ids).handle(
        AddService(master_id, "Тестовая", 30, None)
    )
    await ArchiveServiceHandler(world.uow(), world.clock).handle(ArchiveService(master_id, short))
    world.clock.advance(timedelta(days=1))
    await ArchiveServiceHandler(world.uow(), world.clock).handle(ArchiveService(master_id, long))
    assert await removed.handle(ListRemovedServices(master_id)) == ("Чистка лица", "Массаж спины")
    await AddServiceHandler(world.uow(), world.clock, world.ids).handle(
        AddService(master_id, "массаж СПИНЫ", 40, None)
    )
    assert await removed.handle(ListRemovedServices(master_id)) == ("Чистка лица",)
    world.clock.advance(timedelta(days=31))
    assert await removed.handle(ListRemovedServices(master_id)) == ()


async def test_portfolio_and_days_off(world: World) -> None:
    master_id, _, _ = await world.published_master()
    photo = uuid4()
    await ReplacePortfolioHandler(world.uow(), world.clock).handle(
        ReplacePortfolio(master_id, ((photo, "https://cdn.beautiful.kz/1.jpg", "Чистка"),))
    )
    page = await GetMasterPageHandler(world.readers).handle(GetMasterPage("alisa"))
    assert page.photos[0].id == photo
    # «Сегодня» — по поясу мастера: 15 окт 17:00 в Алматы; 14-е — прошлое.
    await SetDaysOffHandler(world.uow(), world.clock).handle(
        SetDaysOff(master_id, (date(2026, 10, 14), date(2026, 10, 16)))
    )
    assert world.store.masters[master_id].days_off == (date(2026, 10, 16),)


async def test_slots_default_to_shortest_service(world: World) -> None:
    _, short, long = await world.published_master()
    found = await world.slots().handle(ListFreeSlots("alisa", limit=3))
    assert {s.service_id for s in found} == {short}
    # 17:00 + min notice 60 мин → 18:00; 18:00 + 40 мин помещается до 19:00.
    assert [s.start.strftime("%d %H:%M") for s in found] == ["15 18:00", "16 10:00", "16 10:30"]
    assert found[0].start.utcoffset() == timedelta(hours=5)

    longer = await world.slots().handle(ListFreeSlots("alisa", service_id=long, limit=1))
    assert longer[0].service_id == long
    assert longer[0].start.strftime("%d %H:%M") == "16 10:00"


async def test_slots_use_busy_source_within_bounds(world: World) -> None:
    master_id, short, _ = await world.published_master()
    tz = world.store.masters[master_id].timezone.zone()
    world.busy.intervals = [
        TimeInterval(datetime(2026, 10, 16, 10, tzinfo=tz), datetime(2026, 10, 16, 12, tzinfo=tz))
    ]
    found = await world.slots().handle(
        ListFreeSlots(
            "alisa",
            service_id=short,
            window_from=datetime(2026, 10, 16, 0, tzinfo=tz),
            window_to=datetime(2026, 10, 16, 13, tzinfo=tz),
        )
    )
    # Окна, начинающиеся в [from, to): 12:30–13:10 начинается до 13:00.
    assert [s.start.strftime("%H:%M") for s in found] == ["12:00", "12:30"]
    assert world.busy.requested is not None
    assert world.busy.requested[0] == master_id


@pytest.mark.parametrize(
    "query",
    [
        ListFreeSlots("alisa", limit=0),
        ListFreeSlots("alisa", limit=101),
        ListFreeSlots("alisa", window_from=datetime(2026, 10, 16)),
        ListFreeSlots(
            "alisa",
            window_from=datetime(2026, 10, 17, tzinfo=datetime.now().astimezone().tzinfo),
            window_to=datetime(2026, 10, 16, tzinfo=datetime.now().astimezone().tzinfo),
        ),
    ],
)
async def test_invalid_slot_window(world: World, query: ListFreeSlots) -> None:
    await world.published_master()
    with pytest.raises(InvalidSlotWindowError):
        await world.slots().handle(query)


async def test_unknown_service(world: World) -> None:
    await world.published_master()
    with pytest.raises(ServiceNotFoundError):
        await world.slots().handle(ListFreeSlots("alisa", service_id=uuid4()))


async def test_assign_owner_and_find_draft_page(world: World) -> None:
    master_id, _, _ = await world.published_master()
    await AssignOwnerHandler(world.uow(), world.clock).handle(AssignOwner("alisa", "+77051238967"))
    found = await FindMasterByOwnerHandler(world.readers).handle(FindMasterByOwner("+77051238967"))
    assert found == master_id
    other = await RegisterMasterHandler(world.uow(), world.clock, world.ids).handle(
        RegisterMaster("dana", "Дана", "Дана", "Даны", "Дане")
    )
    with pytest.raises(OwnerTakenError):
        await AssignOwnerHandler(world.uow(), world.clock).handle(AssignOwner("dana", "+77051238967"))
    with pytest.raises(MasterNotFoundError):
        await GetMasterPageHandler(world.readers).handle(GetMasterPage(other))
    draft = await GetMasterPageHandler(world.readers).handle(GetMasterPage(other, published_only=False))
    assert draft.slug == "dana"
    with pytest.raises(InvalidProfile):
        await AssignOwnerHandler(world.uow(), world.clock).handle(AssignOwner("dana", "87051238967"))
