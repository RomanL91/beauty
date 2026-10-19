"""Расшифровка голосовых на реальном PostgreSQL: голосовое клиента в чате и голосовое
поручение мастера. Сервис распознавания — сценарный (запросы к OpenRouter проверены unit-тестами).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DemoMasterSeeder
from beauty.contexts.agent.application.commands import AnswerClient
from beauty.contexts.agent.application.office import NOT_CONNECTED, TranscribeOfficeTask
from beauty.contexts.agent.presentation.consumers import FrontDeskConsumer
from beauty.contexts.conversations.application.commands import TranscribeVoice
from beauty.entrypoints.api import ApiApplicationFactory
from beauty.shared.application.speech import SpeechToText, VoiceTranscriber
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.speech import ScriptedSpeechToText
from tests.integration.helpers import EventPump, login
from tests.integration.test_booking import BASE, Client, new_client, parse_sse
from tests.integration.test_office import feed

pytestmark = pytest.mark.integration

API = "/api/v1"
OWNER_PHONE = "+77010012001"
AUDIO = b"\x1aE\xdf\xa3" + b"opus" * 256


@pytest.fixture(scope="session")
def app(container: ApplicationContainer) -> FastAPI:
    """Приложение без realtime-моста."""
    return ApiApplicationFactory(container, enable_realtime_bridge=False).create()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP-клиент поверх ASGI."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        yield client


@pytest.fixture
async def master(http: httpx.AsyncClient, container: ApplicationContainer) -> dict[str, str]:
    """Демо-мастер; заголовки его кабинета."""
    await DemoMasterSeeder(container.mediator).seed(OWNER_PHONE)
    token = await login(http, container.mediator, 12001, OWNER_PHONE[1:])
    return {"Authorization": f"Bearer {token}"}


class Recorder:
    """Медиатор ресепшна: запоминает ходы агента вместо запуска runtime."""

    def __init__(self) -> None:
        """Пусто."""
        self.turns: list[AnswerClient] = []

    async def send(self, command: Any) -> None:
        """Запомнить ход."""
        self.turns.append(command)


class ScriptedTranscription(IntegrationEventHandler):
    """Консьюмер расшифровки, как в worker, но со сценарным распознавателем."""

    def __init__(self, container: ApplicationContainer, speech: SpeechToText) -> None:
        """Обработчики расшифровки чата и поручений с этим распознавателем."""
        transcriber = VoiceTranscriber(container.file_storage, speech)
        self._chat = container.conversations.transcribe_handler(transcriber)
        self._office = container.agent.office_transcribe_handler(transcriber)

    async def handle(self, envelope: EventEnvelope) -> None:
        """Голосовое в чате или голосовое поручение."""
        payload = envelope.payload
        if envelope.routing_key == "conversations.message.added" and payload["kind"] == "voice":
            await self._chat.handle(TranscribeVoice(UUID(payload["message_id"])))
        elif envelope.routing_key == "agent.office.task_given" and payload["text"] is None:
            await self._office.handle(
                TranscribeOfficeTask(UUID(payload["master_id"]), UUID(payload["message_id"]))
            )


def pump(container: ApplicationContainer, text: str, recorder: Recorder) -> EventPump:
    """Доставка событий: распознаватель отвечает ``text``, ходы ресепшна записываются."""
    transcription = ScriptedTranscription(container, ScriptedSpeechToText(text))
    return EventPump(
        container,
        {
            "conversations.voice": transcription,
            "agent.office_voice": transcription,
            "agent.front_desk": FrontDeskConsumer(recorder),  # type: ignore[arg-type]
        },
    )


async def send_voice(http: httpx.AsyncClient, url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Голосовое (multipart)."""
    response = await http.post(
        url,
        files={"audio": ("voice.webm", AUDIO, "audio/webm;codecs=opus")},
        data={"client_id": str(uuid4()), "duration": "3.4"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_client_voice_is_transcribed_and_answered_by_text(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Голосовое → текст под ним (обновлением в ленте) → ход агента по тексту."""
    recorder = Recorder()
    client: Client = await new_client(http, container, 12011)
    voice = await send_voice(http, f"{API}/conversations/{client.conversation_id}/messages", client.headers)
    assert voice["transcript"] is None
    delivered = await pump(container, "Можно записаться на завтра?", recorder).drain()

    assert "conversations.voice.transcribed" in delivered
    (stored,) = [m for m in await client.history() if m["id"] == voice["id"]]
    assert stored["transcript"] == "Можно записаться на завтра?"
    updates = [f["data"]["message"] for f in await client.events("0") if f["event"] == "message.updated"]
    assert (updates[-1]["id"], updates[-1]["transcript"]) == (voice["id"], "Можно записаться на завтра?")
    dialog = await http.get(f"{API}/me/conversations/{client.conversation_id}/messages", headers=master)
    assert dialog.json()["items"][-1]["transcript"] == "Можно записаться на завтра?"

    assert [(str(t.message_id), t.text) for t in recorder.turns] == [
        (voice["id"], "Можно записаться на завтра?")
    ]

    await pump(container, "Другой текст", recorder).drain()  # повтор события — без новой расшифровки
    assert len(recorder.turns) == 1


async def test_failed_transcription_goes_to_master(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Распознать не вышло (тишина) — голосовое без текста, агент получает ход без текста."""
    recorder = Recorder()
    client = await new_client(http, container, 12021)
    voice = await send_voice(http, f"{API}/conversations/{client.conversation_id}/messages", client.headers)
    await pump(container, "   ", recorder).drain()
    (stored,) = [m for m in await client.history() if m["id"] == voice["id"]]
    assert stored["transcript"] is None
    assert [(str(t.message_id), t.text) for t in recorder.turns] == [(voice["id"], None)]


async def test_voice_task_is_transcribed_before_the_turn(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Голосовое поручение: текст — в ленте кабинета, ход — один, после расшифровки."""
    task = await send_voice(http, f"{API}/me/assistant/messages", master)
    assert (task["kind"], task["transcript"]) == ("voice", None)
    stream = asyncio.create_task(http.get(f"{API}/me/events", headers=master))
    await asyncio.sleep(0.1)
    await pump(container, "Что у меня завтра?", Recorder()).drain()
    items = await feed(http, master)
    assert [(m["author"], m["kind"], m.get("transcript") or m.get("text")) for m in items] == [
        ("master", "voice", "Что у меня завтра?"),
        ("agent", "system", NOT_CONNECTED),  # runtime в тестах выключен — ход был, один
    ]
    frames = parse_sse((await asyncio.wait_for(stream, timeout=5)).text)
    assert any(
        f["event"] == "message.updated" and f["data"]["message"].get("transcript") == "Что у меня завтра?"
        for f in frames
    )
