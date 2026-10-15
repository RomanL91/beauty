"""Адаптеры Telegram для Identity."""

from __future__ import annotations

from urllib.parse import quote

from beauty.contexts.identity.application.ports import DeepLinkBuilder
from beauty.contexts.identity.domain.value_objects import AuthNonce


class TelegramDeepLinkBuilder(DeepLinkBuilder):
    """Строит ссылку ``https://t.me/<bot>?start=<nonce>``."""

    def __init__(self, bot_username: str) -> None:
        """Запомнить имя бота (без ``@``)."""
        self._bot_username = bot_username.lstrip("@")

    def build(self, nonce: AuthNonce) -> str:
        """Ссылка, открывающая бота с параметром ``start``."""
        return f"https://t.me/{quote(self._bot_username)}?start={nonce.value}"
