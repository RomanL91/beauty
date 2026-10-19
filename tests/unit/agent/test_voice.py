"""Голосовые для агента: ход — по расшифровке, а не по самому голосовому."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from beauty.contexts.agent.application.commands import AnswerClient
from beauty.contexts.agent.application.office import RunOfficeTurn
from beauty.contexts.agent.domain.events import OfficeFeedChanged, OfficeTaskGiven, OfficeVoiceTranscribed
from beauty.contexts.agent.domain.office import OfficeMessage, OfficeVoice
from beauty.contexts.agent.presentation.consumers import (
    VOICE_TRANSCRIBED,
    BackOfficeConsumer,
    FrontDeskConsumer,
)
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope

NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
MASTER = UUID(int=1)
CONVERSATION = UUID(int=2)


def envelope(routing_key: str, **payload: Any) -> EventEnvelope:
    """Событие из брокера."""
    return EventEnvelope(uuid4(), routing_key, "Event", 1, NOW, payload)


class Recorder:
    """Медиатор, запоминающий команды."""

    def __init__(self) -> None:
        """Пусто."""
        self.sent: list[Any] = []

    async def send(self, command: Any) -> None:
        """Запомнить."""
        self.sent.append(command)


async def test_front_desk_answers_text_and_transcribed_client_voice() -> None:
    """Текст — сразу; голосовое — по расшифровке клиента (не вышло — ``text=None``, передача мастеру)."""
    mediator = Recorder()
    consumer = FrontDeskConsumer(mediator)  # type: ignore[arg-type]
    posted = "conversations.client.message_posted"
    voice_id, text_id = uuid4(), uuid4()
    common = {"conversation_id": str(CONVERSATION)}
    await consumer.handle(envelope(posted, **common, message_id=str(uuid4()), intent="voice", text=None))
    await consumer.handle(envelope(posted, **common, message_id=str(uuid4()), intent="book_slot"))
    await consumer.handle(envelope(posted, **common, message_id=str(text_id), intent="text", text="Привет"))
    await consumer.handle(
        envelope(VOICE_TRANSCRIBED, **common, message_id=str(voice_id), author="client", text="На завтра")
    )
    await consumer.handle(
        envelope(VOICE_TRANSCRIBED, **common, message_id=str(uuid4()), author="client", text=None)
    )
    await consumer.handle(
        envelope(VOICE_TRANSCRIBED, **common, message_id=str(uuid4()), author="master", text="Да")
    )
    assert [(c.message_id, c.text) for c in mediator.sent[:2]] == [
        (text_id, "Привет"),
        (voice_id, "На завтра"),
    ]
    assert [type(c) for c in mediator.sent] == [AnswerClient] * 3
    assert mediator.sent[2].text is None


def test_office_voice_task_waits_for_transcript() -> None:
    """Голосовое поручение: ход — после расшифровки, с тем же ключом идемпотентности."""
    task_id = str(uuid4())
    given = envelope(OfficeTaskGiven.routing_key, master_id=str(MASTER), message_id=task_id, text=None)
    assert BackOfficeConsumer.command(given) is None
    done = envelope(
        OfficeVoiceTranscribed.routing_key,
        master_id=str(MASTER),
        message_id=task_id,
        text="Что у меня завтра?",
    )
    assert BackOfficeConsumer.command(done) == RunOfficeTurn(MASTER, "Что у меня завтра?", task_id)
    failed = envelope(
        OfficeVoiceTranscribed.routing_key, master_id=str(MASTER), message_id=task_id, text=None
    )
    assert BackOfficeConsumer.command(failed) == RunOfficeTurn(MASTER, None, task_id)


def test_office_voice_gets_transcript_once() -> None:
    """Расшифровка — обновлением сообщения в ленте и событием агенту; повтор — no-op."""
    task = OfficeMessage.from_master(
        message_id=UUID(int=6),
        master_id=MASTER,
        client_message_id=UUID(int=7),
        content=OfficeVoice("voice/2026/10/x.webm", 4.0),
        now=NOW,
    )
    task.pull_events()
    assert task.snapshot()["transcript"] is None
    assert task.transcribed("Закрой воскресенье", NOW)
    changed, transcribed = task.pull_events()
    assert isinstance(changed, OfficeFeedChanged)
    assert (changed.change, changed.message["transcript"]) == ("message.updated", "Закрой воскресенье")
    assert isinstance(transcribed, OfficeVoiceTranscribed)
    assert transcribed.text == "Закрой воскресенье"
    assert not task.transcribed("Другое", NOW)
    assert task.pull_events() == []

    failed = OfficeMessage.from_master(
        message_id=UUID(int=8),
        master_id=MASTER,
        client_message_id=UUID(int=9),
        content=OfficeVoice("voice/2026/10/y.webm", 2.0),
        now=NOW,
    )
    failed.pull_events()
    assert failed.transcribed(None, NOW)
    (event,) = failed.pull_events()  # ленту не трогаем: текста нет
    assert isinstance(event, OfficeVoiceTranscribed)
    assert event.text is None
