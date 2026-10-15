"""Помощники интеграционных тестов: прохождение входа через медиатор."""

from __future__ import annotations

from beauty.contexts.identity.application.commands import (
    ClaimChallenge,
    CompleteChallengeWithContact,
    ConfirmChallengeCode,
    StartTelegramAuth,
)
from beauty.contexts.identity.application.dto import StartedChallenge
from beauty.shared.application.mediator import Mediator


class BotSimulator:
    """Действия пользователя в Telegram-боте, выраженные командами медиатора."""

    def __init__(self, mediator: Mediator) -> None:
        """Получить медиатор."""
        self._mediator = mediator

    @staticmethod
    def nonce_of(deep_link: str) -> str:
        """Параметр ``start`` из deep link."""
        return deep_link.rsplit("start=", 1)[1]

    async def confirm(self, deep_link: str, code: str, telegram_user: int) -> None:
        """Открыть ссылку и выбрать код."""
        nonce = self.nonce_of(deep_link)
        await self._mediator.send(ClaimChallenge(nonce, telegram_user))
        await self._mediator.send(ConfirmChallengeCode(nonce, telegram_user, code))

    async def share_contact(self, telegram_user: int, phone: str) -> None:
        """Поделиться своим контактом."""
        await self._mediator.send(CompleteChallengeWithContact(telegram_user, telegram_user, phone))

    async def start_and_confirm(self, telegram_user: int) -> StartedChallenge:
        """Начать вход (как браузер) и подтвердить код (как бот)."""
        started = await self._mediator.send(StartTelegramAuth())
        await self.confirm(started.deep_link, started.confirmation_code, telegram_user)
        return started
