"""Адаптеры распознавания речи: OpenRouter, сценарный (разработка, стенд) и выключенный."""

from __future__ import annotations

import base64
import logging
import time

import httpx

from beauty.shared.application.speech import SpeechToText, TranscriptionFailed

logger = logging.getLogger(__name__)


class OpenRouterSpeechToText(SpeechToText):
    """``POST {base}/audio/transcriptions`` OpenRouter: аудио base64 в JSON, ответ — ``text``.

    Язык по умолчанию определяется сам (клиенты пишут по-русски и по-казахски, бывает
    вперемешку). ``zdr`` — только провайдеры без хранения данных (Zero Data Retention).
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        language: str | None = None,
        zdr: bool = True,
    ) -> None:
        """Ключ OpenRouter, модель распознавания и параметры запроса."""
        self._http = http
        self._url = f"{base_url.rstrip('/')}/audio/transcriptions"
        self._api_key = api_key
        self._model = model
        self._language = language
        self._zdr = zdr

    @property
    def enabled(self) -> bool:
        """Да."""
        return True

    async def transcribe(self, audio: bytes, audio_format: str) -> str:
        """Расшифровать запись."""
        body: dict[str, object] = {
            "model": self._model,
            "input_audio": {"data": base64.b64encode(audio).decode(), "format": audio_format},
        }
        if self._language:
            body["language"] = self._language
        if self._zdr:
            body["provider"] = {"zdr": True}
        started = time.monotonic()
        try:
            response = await self._http.post(
                self._url, headers={"Authorization": f"Bearer {self._api_key}"}, json=body
            )
        except httpx.HTTPError as error:
            raise TranscriptionFailed(f"OpenRouter недоступен: {error!r}") from error
        if response.status_code != 200:
            raise TranscriptionFailed(f"OpenRouter {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
            text = str(payload.get("text") or "")
        except ValueError as error:
            raise TranscriptionFailed("OpenRouter: ответ не JSON") from error
        usage = payload.get("usage") or {}
        logger.info(
            "Расшифровка %s: %d Б за %.1f с, %s с аудио, $%s",
            self._model,
            len(audio),
            time.monotonic() - started,
            usage.get("seconds"),
            usage.get("cost"),
        )
        return text


class ScriptedSpeechToText(SpeechToText):
    """Сценарный распознаватель для разработки и стенда без ключа: любой записи — одна фраза."""

    def __init__(self, text: str) -> None:
        """Фраза «расшифровки»."""
        self._text = text

    @property
    def enabled(self) -> bool:
        """Да."""
        return True

    async def transcribe(self, audio: bytes, audio_format: str) -> str:
        """Фраза (пустая запись — как тишина)."""
        return self._text if audio else ""


class DisabledSpeechToText(SpeechToText):
    """Распознавание выключено: голосовые остаются без текста (агент передаёт их мастеру)."""

    @property
    def enabled(self) -> bool:
        """Нет."""
        return False

    async def transcribe(self, audio: bytes, audio_format: str) -> str:
        """Не вызывается."""
        raise TranscriptionFailed("Распознавание речи выключено")
