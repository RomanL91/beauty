"""Сообщения ленты поручений → JSON контракта (``Message``); ссылки на голосовые — подписанные."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from beauty.shared.infrastructure.storage.signing import SignedMediaUrls


class OfficeRenderer:
    """Снимок сообщения (``OfficeMessage.snapshot``) в форме API."""

    def __init__(self, media: SignedMediaUrls) -> None:
        """Получить подписчика ссылок."""
        self._media = media

    def render(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        """Сообщение в форме контракта."""
        payload = dict(snapshot)
        audio_key = payload.pop("audio_key", None)
        if audio_key is not None:
            payload["audio_url"] = self._media.url(str(audio_key))
        return payload
