"""Ход ресепшна и инструменты MCP на двойниках."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from beauty.contexts.agent.application.commands import (
    FAILURE_NOTE,
    VOICE_NOTE,
    AnswerClient,
    AnswerClientHandler,
)
from beauty.contexts.agent.application.errors import UnknownProfileTokenError
from beauty.contexts.agent.application.instructions import CATALOG_NOTE, front_desk_instructions
from beauty.contexts.agent.application.ports import RunOutcome, RunRequest, ServiceBrief
from beauty.contexts.agent.application.toolkit import FrontDeskToolkit
from beauty.contexts.agent.domain.errors import InvalidTicket
from beauty.contexts.agent.domain.profile import AgentProfile
from beauty.contexts.agent.domain.ticket import RunTicket
from tests.fakes import FrozenClock
from tests.unit.agent.fakes import (
    BRIEF,
    CLIENT,
    CONVERSATION,
    MASTER,
    SERVICE,
    AgentStore,
    FakeBooking,
    InMemoryAgentUnitOfWork,
    Masters,
    RecordingConversations,
    ScriptedRuntime,
)

TOKEN = "mcp-token-of-alisa"


class World:
    """Хранилище, часы, двойники и фабрики."""

    def __init__(self, clock: FrozenClock, handler: str = "agent") -> None:
        """Мастер с профилем агента."""
        self.clock = clock
        self.store = AgentStore()
        self.store.profiles[MASTER] = AgentProfile.register(
            master_id=MASTER,
            profile_name="m-alisa",
            runs_api_key="runs-key",
            mcp_token=TOKEN,
            now=clock.now(),
        )
        self.conversations = RecordingConversations(handler)
        self.booking = FakeBooking(clock.now())
        self.masters = Masters()

    def uow(self) -> InMemoryAgentUnitOfWork:
        """Unit of Work."""
        return InMemoryAgentUnitOfWork(self.store)

    def toolkit(self) -> FrontDeskToolkit:
        """Инструменты ресепшна."""
        return FrontDeskToolkit(self.uow, Masters(), self.booking, self.conversations, self.clock)

    async def answer(self, runtime: ScriptedRuntime, text: str | None = "Хочу на массаж завтра") -> None:
        """Ход ресепшна."""
        handler = AnswerClientHandler(
            self.uow, runtime, self.masters, self.conversations, self.clock, timedelta(minutes=10)
        )
        await handler.handle(AnswerClient(CONVERSATION, CONVERSATION, text))


async def test_turn_books_through_tools_and_replies(clock: FrozenClock) -> None:
    world = World(clock)
    tools = world.toolkit()

    async def script(request: RunRequest) -> str:
        ticket = request.instructions.split("Тикет хода: ")[1].split(" ")[0]
        caller = await tools.authorize(TOKEN, "m-alisa", ticket)
        found = await tools.find_free_slots(caller, str(SERVICE.id))
        booked = await tools.book_appointment(caller, str(SERVICE.id), found["slots"][1]["start"])
        assert booked["ok"], booked
        return "Записала вас на завтра, Алиса подтвердит."

    runtime = ScriptedRuntime(script)
    await world.answer(runtime)
    (request,) = runtime.requests
    assert (request.profile_name, request.api_key) == ("m-alisa", "runs-key")
    assert (request.session_id, request.idempotency_key) == (str(CONVERSATION), str(CONVERSATION))
    assert world.booking.requests[0][0] == CLIENT  # клиент — из тикета
    assert world.conversations.replies == [("Записала вас на завтра, Алиса подтвердит.", True)]
    (run,) = world.store.runs  # журнал ходов — для отчётов панели
    assert (run.status, run.face, run.conversation_id, run.failed) == (
        "completed",
        "front_desk",
        CONVERSATION,
        False,
    )


async def test_turn_skipped_or_handed_off(clock: FrozenClock) -> None:
    disabled = World(clock)
    await disabled.answer(ScriptedRuntime(enabled=False))
    master_leads = World(clock, handler="master")
    await master_leads.answer(ScriptedRuntime())
    assert disabled.conversations.replies == master_leads.conversations.replies == []

    voice = World(clock)
    runtime = ScriptedRuntime()
    await voice.answer(runtime, text=None)
    assert (runtime.requests, voice.conversations.handoffs) == ([], [VOICE_NOTE])

    failing = World(clock)

    async def broken(_request: RunRequest) -> RunOutcome:
        return RunOutcome("timeout")

    await failing.answer(ScriptedRuntime(broken))
    assert failing.conversations.handoffs == [FAILURE_NOTE]
    assert [(r.status, r.failed) for r in failing.store.runs] == [("timeout", True)]

    off = World(clock)
    off.store.profiles[MASTER].set_enabled(False, clock.now())
    await off.answer(ScriptedRuntime())
    assert off.conversations.replies == []


async def test_handoff_keeps_question_for_master(clock: FrozenClock) -> None:
    world = World(clock)
    tools = world.toolkit()

    async def script(request: RunRequest) -> str:
        ticket = request.instructions.split("Тикет хода: ")[1].split(" ")[0]
        caller = await tools.authorize(TOKEN, None, ticket)
        await tools.handoff_to_master(caller, "спрашивает про парковку")
        return "Уточню у Алисы и отвечу здесь."

    await world.answer(ScriptedRuntime(script))
    assert world.conversations.handoffs == ["Агент передал вам: спрашивает про парковку"]
    assert world.conversations.replies == [("Уточню у Алисы и отвечу здесь.", False)]


async def test_tool_authorization(clock: FrozenClock) -> None:
    world = World(clock)
    tools = world.toolkit()
    ticket = RunTicket.issue(
        master_id=MASTER,
        conversation_id=CONVERSATION,
        client_id=CLIENT,
        now=clock.now(),
        ttl=timedelta(minutes=10),
    )
    world.store.tickets[ticket.id] = ticket
    assert ticket.id.startswith("t-")
    assert len(ticket.id) == 10

    with pytest.raises(UnknownProfileTokenError):
        await tools.authorize("чужой токен", None, ticket.id)
    with pytest.raises(UnknownProfileTokenError):
        await tools.authorize(TOKEN, "m-other", ticket.id)
    with pytest.raises(InvalidTicket):
        await tools.authorize(TOKEN, None, "t-unknown1")
    foreign = RunTicket.issue(
        master_id=CLIENT,
        conversation_id=CONVERSATION,
        client_id=CLIENT,
        now=clock.now(),
        ttl=timedelta(minutes=10),
    )
    world.store.tickets[foreign.id] = foreign
    with pytest.raises(InvalidTicket):
        await tools.authorize(TOKEN, None, foreign.id)
    caller = await tools.authorize(TOKEN, "m-alisa", f" {ticket.id} ")
    assert caller.master_id == MASTER

    assert (await tools.find_free_slots(caller, "не uuid"))["ok"] is False
    assert (await tools.book_appointment(caller, str(SERVICE.id), "2020-01-01T10:00:00+05:00"))["ok"] is False
    assert (await tools.my_appointments(caller))["appointments"] == []
    clock.advance(timedelta(minutes=11))
    with pytest.raises(InvalidTicket):
        await tools.authorize(TOKEN, None, ticket.id)


async def test_ticket_of_previous_turn_acts_as_current(clock: FrozenClock) -> None:
    """Модель повторяет тикет прошлого хода из истории — действует тикет текущего хода той же переписки."""
    world = World(clock)
    tools = world.toolkit()

    def issue(conversation: UUID) -> RunTicket:
        ticket = RunTicket.issue(
            master_id=MASTER,
            conversation_id=conversation,
            client_id=CLIENT,
            now=clock.now(),
            ttl=timedelta(minutes=10),
        )
        world.store.tickets[ticket.id] = ticket
        return ticket

    stale = issue(CONVERSATION)
    clock.advance(timedelta(hours=2))
    with pytest.raises(InvalidTicket):
        await tools.authorize(TOKEN, None, stale.id)
    current = issue(CONVERSATION)
    clock.advance(timedelta(seconds=1))
    other = issue(uuid4())

    assert (await tools.authorize(TOKEN, None, stale.id)).ticket_id == current.id
    assert (await tools.authorize(TOKEN, None, current.id)).ticket_id == current.id
    assert (await tools.authorize(TOKEN, None, other.id)).ticket_id == other.id
    clock.advance(timedelta(minutes=11))
    with pytest.raises(InvalidTicket):
        await tools.authorize(TOKEN, None, stale.id)


async def test_turn_after_page_change_says_old_catalog_is_stale(clock: FrozenClock) -> None:
    """История сессии хранит прошлые перечни услуг: после правки страницы ход начинается
    с заметки, что верен только перечень инструкций этого хода."""
    world = World(clock)
    runtime = ScriptedRuntime()

    async def ask() -> RunRequest:
        clock.advance(timedelta(minutes=1))
        await world.answer(runtime, "Какие у вас услуги?")
        return runtime.requests[-1]

    first = await ask()
    assert first.input == "Какие у вас услуги?"  # первый ход нити — без заметки

    facial = ServiceBrief(uuid4(), "Массаж лица", 45, 1_000_000)
    world.masters.current = replace(BRIEF, services=(SERVICE, facial))
    added = await ask()
    assert added.input == f"{CATALOG_NOTE}\n\nКакие у вас услуги?"
    assert "Массаж лица — 45 мин, 10 000 ₸" in added.instructions

    assert (await ask()).input == "Какие у вас услуги?"  # страница та же — без заметки

    world.masters.current = BRIEF
    removed = await ask()
    assert removed.input.startswith(CATALOG_NOTE)
    assert "Массаж лица" not in removed.instructions
    assert "верь только этому списку" in removed.instructions


def test_instructions_carry_catalog_and_ticket(clock: FrozenClock) -> None:
    text = front_desk_instructions(BRIEF, "Новый клиент · …89 67", "t-abcdefgh", clock.now())
    assert "Тикет хода: t-abcdefgh " in text
    assert f"service_id: {SERVICE.id}" in text
    assert "Массаж спины — 60 мин, 12 000 ₸" in text
    assert "четверг, 15.10.2026 17:00 (Asia/Almaty)" in text
