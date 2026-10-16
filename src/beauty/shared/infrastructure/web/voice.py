"""Приём голосового сообщения (``multipart/form-data`` контракта ``VoiceUpload``)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from starlette.datastructures import UploadFile
from starlette.requests import Request

from beauty.shared.application.errors import ApplicationError
from beauty.shared.application.storage import FileStorage

MAX_VOICE_BYTES = 5 * 1024 * 1024
VOICE_EXTENSIONS = {"audio/webm": ".webm", "audio/mp4": ".m4a", "audio/aac": ".m4a", "audio/ogg": ".ogg"}


class InvalidVoiceError(ApplicationError):
    """Нужны поля audio (webm, mp4 или ogg), client_id и duration до 120 с."""

    code = "invalid_voice"


class VoiceTooLargeError(ApplicationError):
    """Голосовое больше 5 МБ."""

    code = "voice_too_large"


@dataclass(frozen=True, slots=True)
class VoiceUpload:
    """Сохранённое голосовое: ключ в хранилище, длительность и id отправителя."""

    client_message_id: UUID
    audio_key: str
    duration: float


class VoiceUploadReader:
    """Проверяет форму и пишет запись в хранилище потоком (с ограничением размера)."""

    def __init__(self, storage: FileStorage, max_seconds: float) -> None:
        """Хранилище и предельная длительность."""
        self._storage = storage
        self._max_seconds = max_seconds

    async def read(self, request: Request) -> VoiceUpload:
        """Голосовое из формы или ``InvalidVoiceError`` / ``VoiceTooLargeError``."""
        async with request.form(max_files=1, max_fields=4) as form:
            audio, raw_client_id, raw_duration = (
                form.get("audio"),
                form.get("client_id"),
                form.get("duration"),
            )
            if not isinstance(audio, UploadFile) or not isinstance(raw_client_id, str):
                raise InvalidVoiceError()
            try:
                client_message_id = UUID(raw_client_id)
                duration = float(raw_duration) if isinstance(raw_duration, str) else 0.0
            except ValueError as error:
                raise InvalidVoiceError() from error
            mime = (audio.content_type or "").split(";")[0].strip()
            extension = VOICE_EXTENSIONS.get(mime)
            if extension is None or not 0 < duration <= self._max_seconds:
                raise InvalidVoiceError()
            if audio.size is not None and audio.size > MAX_VOICE_BYTES:
                raise VoiceTooLargeError()
            stored = await self._storage.save("voice", _chunks(audio), mime, extension)
        return VoiceUpload(client_message_id, stored.key, duration)


async def _chunks(upload: UploadFile, size: int = 64 * 1024) -> AsyncIterator[bytes]:
    total = 0
    while chunk := await upload.read(size):
        total += len(chunk)
        if total > MAX_VOICE_BYTES:
            raise VoiceTooLargeError()
        yield chunk
