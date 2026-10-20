"""Опыт мастера: домен, инструкции, инструменты кабинета и ресепшна, интервью о новой услуге."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from beauty.contexts.agent.application.instructions import (
    INTERVIEW_PREFIX,
    front_desk_instructions,
    office_instructions,
)
from beauty.contexts.agent.application.office import StartServiceInterview, StartServiceInterviewHandler
from beauty.contexts.agent.application.playbook import (
    AddPractice,
    AddPracticeHandler,
    EditPractice,
    EditPracticeHandler,
    GetPlaybook,
    GetPlaybookHandler,
    PlaybookView,
    PracticeServiceNotFoundError,
    PracticeView,
    RemovePractice,
    RemovePracticeHandler,
    SetBookingAutonomy,
    SetBookingAutonomyHandler,
)
from beauty.contexts.agent.application.ports import BookedTime, RunRequest
from beauty.contexts.agent.domain.errors import InvalidPractice, PracticesLimit, UnknownPractice
from beauty.contexts.agent.domain.playbook import MAX_PRACTICES, Playbook, PracticeAuthor
from beauty.contexts.agent.presentation.consumers import SERVICES_CHANGED, BackOfficeConsumer
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from tests.fakes import FrozenClock
from tests.unit.agent.fakes import BRIEF, CLIENT, MASTER, SERVICE, Masters, ScriptedRuntime
from tests.unit.agent.test_agent import TOKEN, World
from tests.unit.agent.test_office import NOW, OFFICE_TOKEN, Office

# ─────────────────────────── домен ───────────────────────────


def test_practices_dedupe_limit_revise_forget() -> None:
    """Повтор текста у той же услуги — та же запись; лимит; правка и удаление."""
    playbook = Playbook.open(master_id=MASTER, now=NOW)
    first = playbook.remember(uuid4(), "  Сложное — с утра ", None, PracticeAuthor.AGENT, NOW)
    assert first.text == "Сложное — с утра"
    assert playbook.remember(uuid4(), "сложное — С УТРА", None, PracticeAuthor.MASTER, NOW) is first
    other = playbook.remember(uuid4(), "Сложное — с утра", SERVICE.id, PracticeAuthor.AGENT, NOW)
    assert other is not first  # к услуге — отдельно от общего
    with pytest.raises(InvalidPractice):
        playbook.remember(uuid4(), " ", None, PracticeAuthor.MASTER, NOW)
    with pytest.raises(InvalidPractice):
        playbook.remember(uuid4(), "x" * 501, None, PracticeAuthor.MASTER, NOW)
    later = NOW + timedelta(minutes=5)
    playbook.revise(first.id, "Окрашивания — до обеда", None, later)
    assert (first.text, first.updated_at, playbook.updated_at) == ("Окрашивания — до обеда", later, later)
    playbook.forget(other.id, later)
    assert [p.id for p in playbook.practices] == [first.id]
    with pytest.raises(UnknownPractice):
        playbook.forget(other.id, later)
    for index in range(MAX_PRACTICES - 1):
        playbook.remember(uuid4(), f"запись {index}", None, PracticeAuthor.MASTER, NOW)
    with pytest.raises(PracticesLimit):
        playbook.remember(uuid4(), "лишняя", None, PracticeAuthor.MASTER, NOW)


def test_autonomy_switch() -> None:
    """По умолчанию заявка мастеру; переключение — только при изменении."""
    playbook = Playbook.open(master_id=MASTER, now=NOW)
    assert playbook.auto_confirm is False
    assert playbook.set_autonomy(True, NOW) is True
    assert playbook.set_autonomy(True, NOW) is False


# ─────────────────────────── кабинет (API) ───────────────────────────


async def test_master_edits_playbook() -> None:
    """Мастер добавляет, правит и удаляет записи; чужая услуга — 404; общие — первыми."""
    office = Office()
    playbooks = office.tools()._playbooks
    by_service = await AddPracticeHandler(playbooks).handle(
        AddPractice(MASTER, "Ботокс — только по пятницам", SERVICE.id)
    )
    general = await AddPracticeHandler(playbooks).handle(AddPractice(MASTER, "Сложное — с утра"))
    assert [(p.text, p.service_title, p.author) for p in general.practices] == [
        ("Сложное — с утра", None, "master"),
        ("Ботокс — только по пятницам", "Массаж спины", "master"),
    ]
    with pytest.raises(PracticeServiceNotFoundError):
        await AddPracticeHandler(playbooks).handle(AddPractice(MASTER, "x", uuid4()))
    target = by_service.practices[0].id
    edited = await EditPracticeHandler(playbooks).handle(
        EditPractice(MASTER, target, "Ботокс — пятница, до 4 человек подряд", None)
    )
    assert [p.service_id for p in edited.practices] == [None, None]
    left = await RemovePracticeHandler(playbooks).handle(RemovePractice(MASTER, target))
    assert [p.text for p in left.practices] == ["Сложное — с утра"]
    on = await SetBookingAutonomyHandler(playbooks).handle(SetBookingAutonomy(MASTER, True))
    assert on.auto_confirm is True
    assert (await GetPlaybookHandler(playbooks).handle(GetPlaybook(MASTER))).auto_confirm is True
    with pytest.raises(UnknownPractice):
        await RemovePracticeHandler(Office().tools()._playbooks).handle(RemovePractice(MASTER, target))


# ─────────────────────────── инструкции ───────────────────────────


def _view(auto_confirm: bool = False) -> PlaybookView:
    general = PracticeView(UUID(int=31), "Сложное — с утра", None, None, "agent", NOW, NOW)
    service = PracticeView(
        UUID(int=32), "Не больше двух в день", SERVICE.id, SERVICE.title, "master", NOW, NOW
    )
    return PlaybookView(auto_confirm, (general, service))


def test_instructions_carry_master_experience() -> None:
    """Опыт — в обоих лицах: общий блоком, к услуге — под услугой; у кабинета — с id."""
    front = front_desk_instructions(BRIEF, "Дарья", "t-abcdefgh", NOW, (), _view())
    assert "Как работает Алиса — опыт мастера" in front
    assert "- Сложное — с утра\n" in front
    assert "  Опыт мастера: Не больше двух в день" in front
    assert "это заявка, Алиса её подтвердит" in front
    assert "загрузку этих дней" in front
    assert "запись сразу подтверждена" in front_desk_instructions(
        BRIEF, "Дарья", "t-abcdefgh", NOW, (), _view(auto_confirm=True)
    )
    office = office_instructions(BRIEF, "t-abcdefgh", NOW, _view())
    assert f"- Сложное — с утра [{UUID(int=31)}]" in office
    assert f"  Опыт мастера [{UUID(int=32)}]: Не больше двух в день" in office
    assert "ресепшн оставляет заявку" in office
    assert "предложи коротко познакомиться" not in office
    assert "предложи коротко познакомиться" in office_instructions(BRIEF, "t-abcdefgh", NOW)


# ─────────────────────────── инструменты кабинета ───────────────────────────


async def test_agent_learns_from_master() -> None:
    """Агент запоминает опыт (общий и к услуге), правит, забывает, меняет самостоятельность."""
    office = Office()
    tools = office.tools()
    caller = await tools.authorize(OFFICE_TOKEN, None, office.office_ticket().id)
    general = await tools.remember_practice(caller, "Два окрашивания в день — предел")
    assert general["ok"], general
    about = await tools.remember_practice(caller, "Только по пятницам", str(SERVICE.id))
    assert about["ok"], about
    assert not (await tools.remember_practice(caller, "x", str(uuid4())))["ok"]
    assert not (await tools.remember_practice(caller, "x", "не uuid"))["ok"]
    assert not (await tools.remember_practice(caller, " "))["ok"]
    assert (await tools.revise_practice(caller, general["practice_id"], "Два тяжёлых в день — предел"))["ok"]
    assert (await tools.forget_practice(caller, about["practice_id"]))["ok"]
    assert not (await tools.forget_practice(caller, about["practice_id"]))["ok"]
    playbook = office.store.playbooks[MASTER]
    assert [(p.text, p.author) for p in playbook.practices] == [
        ("Два тяжёлых в день — предел", PracticeAuthor.AGENT)
    ]
    assert (await tools.set_booking_autonomy(caller, True))["auto_confirm"] is True
    assert playbook.auto_confirm is True
    assert (await tools.set_service_description(caller, str(SERVICE.id), "Глубокий массаж"))["ok"]
    assert ("describe", (SERVICE.id, "Глубокий массаж")) in office.cabinet.actions
    assert not (await tools.set_service_description(caller, str(uuid4()), "x"))["ok"]


# ─────────────────────────── ресепшн ───────────────────────────


async def test_front_desk_sees_day_load_and_books_on_its_own(clock: FrozenClock) -> None:
    """Окна — с загрузкой дня без клиентов; мастер доверил — запись сразу подтверждена."""
    world = World(clock)
    playbook = Playbook.open(master_id=MASTER, now=clock.now())
    playbook.set_autonomy(True, clock.now())
    world.store.playbooks[MASTER] = playbook
    first = world.booking.slots[0]
    day = first.astimezone(ZoneInfo(BRIEF.timezone)).date()
    world.booking.load[day] = [BookedTime(first - timedelta(hours=3), first, "Окрашивание", "confirmed")]
    tools = world.toolkit()
    seen: dict[str, object] = {}

    async def script(request: RunRequest) -> str:
        ticket = request.instructions.split("Тикет хода: ")[1].split(" ")[0]
        caller = await tools.authorize(TOKEN, "m-alisa", ticket)
        seen["found"] = await tools.find_free_slots(caller, str(SERVICE.id))
        seen["booked"] = await tools.book_appointment(caller, str(SERVICE.id), first.isoformat())
        return "Записала вас!"

    await world.answer(ScriptedRuntime(script))
    found = seen["found"]
    assert isinstance(found, dict)
    assert found["day_load"] == [
        {
            "date": day.isoformat(),
            "booked": [{"start": "07:00", "end": "10:00", "service": "Окрашивание", "confirmed": True}],
        }
    ]
    booked = seen["booked"]
    assert isinstance(booked, dict)
    assert booked["status"] == "confirmed"
    assert str(booked["note"]).startswith("Записал: запись подтверждена")
    assert world.booking.confirmed == [UUID(int=99)]
    assert world.booking.requests[0][0] == CLIENT


# ─────────────────────────── интервью ───────────────────────────


def test_new_service_starts_interview() -> None:
    """Добавленная услуга → интервью; правка или архив — нет."""

    def envelope(change: str) -> EventEnvelope:
        return EventEnvelope(
            message_id=UUID(int=7),
            routing_key=SERVICES_CHANGED,
            event_type="MasterServicesChanged",
            event_version=1,
            occurred_at=NOW,
            payload={"master_id": str(MASTER), "service_id": str(SERVICE.id), "change": change},
        )

    assert BackOfficeConsumer.command(envelope("added")) == StartServiceInterview(
        MASTER, SERVICE.id, f"{UUID(int=7)}:interview"
    )
    assert BackOfficeConsumer.command(envelope("updated")) is None


async def test_interview_turn_and_quiet_without_agent() -> None:
    """Ход кабинета с репликой об услуге; агент не подключён — лента без служебных строк."""
    office = Office()
    runtime = ScriptedRuntime(lambda _request: _ask())
    await StartServiceInterviewHandler(Masters(), office.turn(runtime)).handle(
        StartServiceInterview(MASTER, SERVICE.id, "e:interview")
    )
    (request,) = runtime.requests
    assert request.input.startswith(f"{INTERVIEW_PREFIX} «Массаж спины» — 60 мин, 12 000 ₸.")
    assert [m.snapshot()["text"] for m in office.feed()] == ["Пара вопросов о новой услуге…"]

    unknown = ScriptedRuntime()
    await StartServiceInterviewHandler(Masters(), office.turn(unknown)).handle(
        StartServiceInterview(MASTER, uuid4(), "e2:interview")
    )
    assert unknown.requests == []

    lonely = Office(office=False)
    await StartServiceInterviewHandler(Masters(), lonely.turn(ScriptedRuntime())).handle(
        StartServiceInterview(MASTER, SERVICE.id, "e3:interview")
    )
    assert lonely.feed() == []


async def _ask() -> str:
    return "Пара вопросов о новой услуге…"
