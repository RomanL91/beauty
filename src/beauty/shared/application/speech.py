"""Распознавание речи: порт и расшифровка голосовых из хранилища.

Голосовые клиентов (в чате) и мастера (поручения) расшифровываются одинаково: файл из
хранилища → сервис распознавания → текст. Сервис — сменный адаптер (OpenRouter,
сценарный для разработки, выключенный); контексты видят только ``VoiceTranscriber``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import PurePosixPath

from beauty.shared.application.storage import FileStorage

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT = 4000

AUDIO_FORMATS = {".webm": "webm", ".m4a": "m4a", ".mp4": "m4a", ".aac": "aac", ".ogg": "ogg", ".wav": "wav"}
"""Расширение файла голосового → формат для сервиса распознавания."""


class TranscriptionFailed(Exception):
    """Сервис не расшифровал запись (недоступен, отказал, вернул пустой текст)."""


class SpeechToText(ABC):
    """Сервис распознавания речи."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Подключён ли сервис (выключенный — ничего не расшифровывает)."""

    @abstractmethod
    async def transcribe(self, audio: bytes, audio_format: str) -> str:
        """Текст записи (``audio_format`` — ``webm``, ``m4a``, …) или ``TranscriptionFailed``."""


class VoiceTranscriber:
    """Расшифровка голосового по ключу файла: любая неудача — ``None`` и запись в журнал."""

    def __init__(self, storage: FileStorage, speech: SpeechToText) -> None:
        """Хранилище файлов и сервис распознавания."""
        self._storage = storage
        self._speech = speech

    @property
    def enabled(self) -> bool:
        """Подключён ли сервис распознавания."""
        return self._speech.enabled

    async def transcript(self, audio_key: str) -> str | None:
        """Текст голосового или ``None`` (сервис выключен, файла нет, распознать не удалось)."""
        if not self._speech.enabled:
            return None
        audio_format = AUDIO_FORMATS.get(PurePosixPath(audio_key).suffix.lower())
        if audio_format is None:
            logger.warning("Голосовое %s: неизвестный формат", audio_key)
            return None
        try:
            audio = b"".join([chunk async for chunk in self._storage.open(audio_key)])
            text = " ".join((await self._speech.transcribe(audio, audio_format)).split())
        except OSError as error:
            logger.warning("Голосовое %s не прочитано: %s", audio_key, error)
            return None
        except TranscriptionFailed as error:
            logger.warning("Голосовое %s не расшифровано: %s", audio_key, error)
            return None
        if not text:
            logger.info("Голосовое %s: речи не распознано", audio_key)
            return None
        return text[:MAX_TRANSCRIPT]
