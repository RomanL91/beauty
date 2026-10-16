"""Кабинет: лента поручений, выбор мастера, ход кабинета и инструменты — на двойниках."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from beauty.contexts.agent.application.errors import UnknownProfileTokenError
from beauty.contexts.agent.application.office import (
    FAILURE_REPLY,
    NOT_CONNECTED,
    VOICE_REPLY,
    AnswerOfficeChoice,
    AnswerOfficeChoiceHandler,
    GiveOfficeTask,
    GiveOfficeTaskHandler,
    ListOfficeMessages,
    ListOfficeMessagesHandler,
    RunOfficeTurn,
    RunOfficeTurnHandler,
)
from beauty.contexts.agent.application.office_tools import OfficeToolkit
from beauty.contexts.agent.application.ports import RunOutcome, RunRequest
from beauty.contexts.agent.application.toolkit import FrontDeskToolkit
from beauty.contexts.agent.domain.errors import ChoiceAlreadyAnswered, InvalidTicket, UnknownChoiceOption
from beauty.contexts.agent.domain.events import OfficeChoiceAnswered, OfficeFeedChanged, OfficeTaskGiven
from beauty.contexts.agent.domain.office import OfficeMessage, OfficeText, choice
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.ticket import AgentFace, RunTicket
from beauty.shared.domain.ids import UuidV7Generator
from beauty.shared.domain.secrets import HashedSecret
from tests.fakes import FrozenClock
from tests.unit.agent.fakes import (
    CLIENT,
    CONVERSATION,
    MASTER,
    SERVICE,
    AgentStore,
    FakeBooking,
    FakeCabinet,
    InMemoryAgentUnitOfWork,
    Masters,
    RecordingConversations,
    ScriptedRuntime,
)

NOW = datetime(2026, 10, 16, 6, 0, tzinfo=UTC)  # пт 11:00 в Алматы
FRONT_TOKEN = "front-token-of-alisa"
OFFICE_TOKEN = "office-token-of-alisa"


class Office:
    """Мастер с профилями ресепшна и кабинета, лента и двойники."""

    def __init__(self, *, office: bool = True) -> None:
        """Мастер Алиса."""
        self.clock = FrozenClock(NOW)
        self.ids = UuidV7Generator()
        self.store = AgentStore()
        profile = AgentProfile.register(
            master_id=MASTER, profile_name="m-alisa", runs_api_key="runs", mcp_token=FRONT_TOKEN, now=NOW
        )
        if office:
            profile.attach_office("m-alisa-office", "office-runs", OFFICE_TOKEN, NOW)
        self.store.profiles[MASTER] = profile
        self.cabinet = FakeCabinet()

    def uow(self) -> InMemoryAgentUnitOfWork:
        """Unit of Work."""
        return InMemoryAgentUnitOfWork(self.store)

    def tools(self) -> OfficeToolkit:
        """Инструменты кабинета."""
        return OfficeToolkit(self.uow, Masters(), FakeBooking(NOW), self.cabinet, self.clock, self.ids)

    def turn(self, runtime: ScriptedRuntime) -> RunOfficeTurnHandler:
        """Обработчик хода кабинета."""
        return RunOfficeTurnHandler(self.uow, runtime, Masters(), self.clock, self.ids, timedelta(minutes=10))

    def feed(self) -> list[OfficeMessage]:
        """Лента по порядку."""
        return sorted(self.store.office.values(), key=lambda m: m.id)

    def office_ticket(self) -> RunTicket:
        """Тикет кабинета в хранилище."""
        ticket = RunTicket.issue_office(master_id=MASTER, now=NOW, ttl=timedelta(minutes=10))
        self.store.tickets[ticket.id] = ticket
        return ticket


# ─────────────────────────── домен ───────────────────────────


def test_choice_card_and_answer() -> None:
    """Карточка: варианты по порядку, «Ничего…» приглушён; выбор — один раз."""
    card = OfficeMessage.from_agent(
        message_id=UUID(int=5),
        master_id=MASTER,
        content=choice("Закрыть воскресенье?", ["Да, закрыть", "Ничего не менять"], "Записей нет"),
        now=NOW,
    )
    snapshot = card.snapshot()
    assert snapshot["choice_id"] == str(UUID(int=5))
    assert snapshot["options"] == [
        {"id": "1", "label": "Да, закрыть", "tone": "default"},
        {"id": "2", "label": "Ничего не менять", "tone": "muted"},
    ]
    assert (snapshot["detail"], snapshot["selected_option_id"], snapshot["ai_generated"]) == (
        "Записей нет",
        None,
        True,
    )
    card.pull_events()

    assert card.choose("1", NOW) is True
    changed, answered = card.pull_events()
    assert isinstance(changed, OfficeFeedChanged)
    assert changed.change == "message.updated"
    assert isinstance(answered, OfficeChoiceAnswered)
    assert (answered.question, answered.answer) == ("Закрыть воскресенье?", "Да, закрыть")
    assert card.choose("1", NOW) is False  # повтор — no-op
    with pytest.raises(ChoiceAlreadyAnswered):
        card.choose("2", NOW)
    with pytest.raises(UnknownChoiceOption):
        card.choose("9", NOW)
    with pytest.raises(ValueError, match="от 2 до 4"):
        choice("Что делаем?", ["Одно"])


def test_master_task_feeds_agent() -> None:
    """Поручение мастера: в ленту (кадр кабинета) и агенту на ход."""
    task = OfficeMessage.from_master(
        message_id=UUID(int=6),
        master_id=MASTER,
        client_message_id=UUID(int=7),
        content=OfficeText("Привет"),
        now=NOW,
    )
    changed, given = task.pull_events()
    assert isinstance(changed, OfficeFeedChanged)
    assert changed.message["author"] == "master"
    assert isinstance(given, OfficeTaskGiven)
    assert given.text == "Привет"
    assert task.snapshot()["client_id"] == str(UUID(int=7))


def test_tokens_open_only_their_role() -> None:
    """Токен ресепшна — ресепшн, токен кабинета — кабинет; профиль роли — по токену."""
    profile = Office().store.profiles[MASTER]
    assert profile.face_of(HashedSecret.of(FRONT_TOKEN)) is AgentFace.FRONT_DESK
    assert profile.face_of(HashedSecret.of(OFFICE_TOKEN)) is AgentFace.BACK_OFFICE
    assert profile.face_of(HashedSecret.of("чужой")) is None
    assert profile.seat(AgentFace.BACK_OFFICE) == ("m-alisa-office", "office-runs")
    assert Office(office=False).store.profiles[MASTER].seat(AgentFace.BACK_OFFICE) is None


# ─────────────────────────── лента ───────────────────────────


async def test_task_is_idempotent_and_choice_is_answered_once() -> None:
    """Повтор отправки — то же сообщение; выбор — 404 на чужое и 409 на другой вариант."""
    world = Office()
    give = GiveOfficeTask(MASTER, UUID(int=8), text="Что у меня завтра?")
    first = await GiveOfficeTaskHandler(world.uow(), world.clock, world.ids).handle(give)
    again = await GiveOfficeTaskHandler(world.uow(), world.clock, world.ids).handle(give)
    assert first == again
    assert len(world.store.office) == 1
    assert [type(e) for e in world.store.events] == [OfficeFeedChanged, OfficeTaskGiven]

    card = OfficeMessage.from_agent(
        message_id=world.ids.new(), master_id=MASTER, content=choice("Да?", ["Да", "Нет"]), now=NOW
    )
    world.store.office[card.id] = card
    answer = AnswerOfficeChoiceHandler(world.uow(), world.clock)
    chosen = await answer.handle(AnswerOfficeChoice(MASTER, card.id, "1"))
    assert chosen["selected_option_id"] == "1"
    assert (await answer.handle(AnswerOfficeChoice(MASTER, card.id, "1")))["selected_option_id"] == "1"
    with pytest.raises(ChoiceAlreadyAnswered):
        await answer.handle(AnswerOfficeChoice(MASTER, card.id, "2"))
    with pytest.raises(UnknownChoiceOption):
        await answer.handle(AnswerOfficeChoice(UUID(int=42), card.id, "1"))

    page = await ListOfficeMessagesHandler(world.uow()).handle(ListOfficeMessages(MASTER, limit=1))
    assert ([m["kind"] for m in page.items], page.has_more) == (["choice"], True)


# ─────────────────────────── ход кабинета ───────────────────────────


async def test_turn_runs_in_office_profile_and_replies() -> None:
    """Ход — в профиле кабинета, сессия на день мастера, тикет кабинета в инструкциях."""
    world = Office()
    runtime = ScriptedRuntime(lambda _request: _text("Завтра две записи."))
    await world.turn(runtime).handle(RunOfficeTurn(MASTER, "Что у меня завтра?", "msg-1"))
    (request,) = runtime.requests
    assert (request.profile_name, request.api_key) == ("m-alisa-office", "office-runs")
    assert request.session_id == f"office-{MASTER}-2026-10-16"
    assert "С тобой говорит сам мастер" in request.instructions
    ticket = next(iter(world.store.tickets.values()))
    assert ticket.face is AgentFace.BACK_OFFICE
    assert f"Тикет хода: {ticket.id}" in request.instructions
    assert [(m.author.value, m.snapshot()["text"]) for m in world.feed()] == [("agent", "Завтра две записи.")]


async def test_turn_that_asked_master_posts_only_the_card() -> None:
    """Ход задал вопрос — ответом служит карточка, итоговый текст хода в ленту не идёт."""
    world = Office()
    tools = world.tools()

    async def script(request: RunRequest) -> str:
        ticket = request.instructions.split("Тикет хода: ")[1].split(" ")[0]
        caller = await tools.authorize(OFFICE_TOKEN, "m-alisa-office", ticket)
        assert (await tools.ask_master(caller, "Закрыть воскресенье?", ["Да", "Ничего не менять"], None))[
            "ok"
        ]
        return "Спросила мастера."

    await world.turn(ScriptedRuntime(script)).handle(RunOfficeTurn(MASTER, "Закрой воскресенье", "msg-2"))
    assert [m.kind for m in world.feed()] == ["choice"]


@pytest.mark.parametrize(
    ("office", "enabled", "text", "expected"),
    [
        (False, True, "Привет", NOT_CONNECTED),
        (True, False, "Привет", NOT_CONNECTED),
        (True, True, None, VOICE_REPLY),
    ],
)
async def test_turn_without_runtime_or_with_voice(
    office: bool, enabled: bool, text: str | None, expected: str
) -> None:
    """Нет профиля кабинета или runtime — служебная строка; голосовое — просьба написать текстом."""
    world = Office(office=office)
    runtime = ScriptedRuntime(enabled=enabled)
    await world.turn(runtime).handle(RunOfficeTurn(MASTER, text, "msg-3"))
    assert runtime.requests == []
    assert [m.snapshot()["text"] for m in world.feed()] == [expected]


async def test_failed_turn_is_reported_to_master() -> None:
    """Ход не удался — предупреждение мастеру."""
    world = Office()
    await world.turn(ScriptedRuntime(lambda _r: _outcome(RunOutcome("timeout")))).handle(
        RunOfficeTurn(MASTER, "Отмени Дарью", "msg-4")
    )
    (message,) = world.feed()
    assert (message.snapshot()["text"], message.snapshot()["tone"], message.ai_generated) == (
        FAILURE_REPLY,
        "warning",
        False,
    )


# ─────────────────────────── инструменты ───────────────────────────


async def test_office_and_front_desk_tokens_do_not_cross() -> None:
    """Токен ресепшна не открывает кабинет, токен кабинета — ресепшн; тикет — своей роли."""
    world = Office()
    office_ticket = world.office_ticket()
    tools = world.tools()
    assert (await tools.authorize(OFFICE_TOKEN, "m-alisa-office", office_ticket.id)).master_id == MASTER
    with pytest.raises(UnknownProfileTokenError):
        await tools.authorize(FRONT_TOKEN, "m-alisa", office_ticket.id)
    with pytest.raises(UnknownProfileTokenError):
        await tools.authorize(OFFICE_TOKEN, "m-alisa", office_ticket.id)

    front_ticket = RunTicket.issue(
        master_id=MASTER, conversation_id=CONVERSATION, client_id=CLIENT, now=NOW, ttl=timedelta(minutes=10)
    )
    world.store.tickets[front_ticket.id] = front_ticket
    with pytest.raises(InvalidTicket):
        await tools.authorize(OFFICE_TOKEN, None, front_ticket.id)
    front = FrontDeskToolkit(world.uow, Masters(), FakeBooking(NOW), RecordingConversations(), world.clock)
    with pytest.raises(UnknownProfileTokenError):
        await front.authorize(OFFICE_TOKEN, None, front_ticket.id)
    with pytest.raises(InvalidTicket):
        await front.authorize(FRONT_TOKEN, None, office_ticket.id)


async def test_office_tools_act_for_the_master() -> None:
    """График, клиенты, отмена, выходной, сообщение клиенту — с понятными отказами."""
    world = Office()
    tools = world.tools()
    caller = await tools.authorize(OFFICE_TOKEN, None, world.office_ticket().id)

    day = await tools.day_schedule(caller, None)
    assert day["date"] == "2026-10-16"
    assert day["items"][0] == {
        "kind": "appointment",
        "appointment_id": str(UUID(int=77)),
        "status": "confirmed",
        "start": "2026-10-16T12:00:00+05:00",
        "end": "2026-10-16T13:00:00+05:00",
        "service": "Массаж спины",
        "client": "Дарья К.",
        "client_id": str(CLIENT),
    }
    assert (await tools.day_schedule(caller, "завтра"))["ok"] is False

    clients = (await tools.find_clients(caller, "Дарья"))["clients"]
    assert clients == [
        {"client_id": str(CLIENT), "name": "Дарья К.", "phone": "+7 705 ••• 89 67", "visits": 2}
    ]

    assert (await tools.cancel_appointment(caller, str(UUID(int=77)), True))["status"] == "cancelled"
    assert (await tools.cancel_appointment(caller, str(UUID(int=1)), True)) == {
        "ok": False,
        "error": "Запись не найдена",
    }
    assert (await tools.set_day_off(caller, "2026-10-18", True))["day_off"] is True
    assert (await tools.message_client(caller, str(CLIENT), "Возьмите полотенце"))["ok"] is True
    assert (await tools.message_client(caller, str(UUID(int=9)), "Привет"))["ok"] is False

    start = (NOW + timedelta(days=1)).replace(hour=5).isoformat()
    booked = await tools.book_client(caller, str(CLIENT), str(SERVICE.id), start)
    assert booked["status"] == "confirmed"
    assert (await tools.book_client(caller, "кто-то", str(SERVICE.id), start))["ok"] is False
    assert [a for a, _ in world.cabinet.actions] == ["cancel", "message", "book"]


def _text(text: str) -> object:
    async def done() -> str:
        return text

    return done()


def _outcome(outcome: RunOutcome) -> object:
    async def done() -> RunOutcome:
        return outcome

    return done()
