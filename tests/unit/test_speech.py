"""Распознавание речи: адаптер OpenRouter (запрос и ответ) и расшифровка голосовых из хранилища."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from beauty.shared.application.speech import SpeechToText, TranscriptionFailed, VoiceTranscriber
from beauty.shared.domain.ids import UuidV7Generator
from beauty.shared.infrastructure.speech import (
    DisabledSpeechToText,
    OpenRouterSpeechToText,
    ScriptedSpeechToText,
)
from beauty.shared.infrastructure.storage.local import LocalFileStorage

AUDIO = b"\x1aE\xdf\xa3" + b"opus" * 64


def openrouter(
    handler: httpx.MockTransport, *, language: str | None = None, zdr: bool = True
) -> OpenRouterSpeechToText:
    """Адаптер поверх подставного транспорта."""
    return OpenRouterSpeechToText(
        httpx.AsyncClient(transport=handler),
        api_key="sk-or-test",
        model="openai/whisper-large-v3",
        language=language,
        zdr=zdr,
    )


async def test_openrouter_request_and_response() -> None:
    """JSON с аудио base64 и форматом, только провайдеры без хранения данных; ответ — ``text``."""
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "Запишите меня на завтра", "usage": {"seconds": 3}})

    text = await openrouter(httpx.MockTransport(respond)).transcribe(AUDIO, "webm")
    assert text == "Запишите меня на завтра"
    (request,) = seen
    assert str(request.url) == "https://openrouter.ai/api/v1/audio/transcriptions"
    assert request.headers["Authorization"] == "Bearer sk-or-test"
    body = json.loads(request.content)
    assert body["model"] == "openai/whisper-large-v3"
    assert body["input_audio"] == {"data": base64.b64encode(AUDIO).decode(), "format": "webm"}
    assert body["provider"] == {"zdr": True}
    assert "language" not in body  # язык определяется сам: русский, казахский, вперемешку

    await openrouter(httpx.MockTransport(respond), language="kk", zdr=False).transcribe(AUDIO, "m4a")
    body = json.loads(seen[-1].content)
    assert (body["language"], "provider" in body, body["input_audio"]["format"]) == ("kk", False, "m4a")


async def test_openrouter_failures() -> None:
    """Отказ сервиса и сеть — ``TranscriptionFailed`` с причиной."""
    refused = openrouter(httpx.MockTransport(lambda _: httpx.Response(402, json={"error": "no credits"})))
    with pytest.raises(TranscriptionFailed, match="402"):
        await refused.transcribe(AUDIO, "webm")

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(TranscriptionFailed, match="недоступен"):
        await openrouter(httpx.MockTransport(offline)).transcribe(AUDIO, "webm")


class Failing(SpeechToText):
    """Сервис, который всегда отказывает."""

    @property
    def enabled(self) -> bool:
        """Да."""
        return True

    async def transcribe(self, audio: bytes, audio_format: str) -> str:
        """Отказ."""
        raise TranscriptionFailed("503")


async def _chunks() -> AsyncIterator[bytes]:
    yield AUDIO


async def test_transcriber_reads_file_and_never_raises(tmp_path: Path) -> None:
    """Текст — без лишних пробелов; выключено, нет файла, отказ, тишина, чужой формат — ``None``."""
    storage = LocalFileStorage(str(tmp_path), UuidV7Generator())
    stored = await storage.save("voice", _chunks(), "audio/webm", ".webm")

    assert await VoiceTranscriber(storage, ScriptedSpeechToText("  Можно\n на завтра? ")).transcript(
        stored.key
    ) == ("Можно на завтра?")
    assert await VoiceTranscriber(storage, DisabledSpeechToText()).transcript(stored.key) is None
    assert await VoiceTranscriber(storage, Failing()).transcript(stored.key) is None
    assert await VoiceTranscriber(storage, ScriptedSpeechToText("   ")).transcript(stored.key) is None
    scripted = VoiceTranscriber(storage, ScriptedSpeechToText("текст"))
    missing = stored.key.rsplit("/", 1)[0] + "/01a154ce-0000-7000-8000-000000000000.webm"
    assert await scripted.transcript(missing) is None
    assert await scripted.transcript(stored.key.replace(".webm", ".flac")) is None
