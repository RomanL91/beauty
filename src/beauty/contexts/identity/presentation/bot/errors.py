"""Показ ошибок пользователю бота."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

from aiogram.types import CallbackQuery, Message

from beauty.shared.application.errors import ApplicationError
from beauty.shared.domain.errors import DomainError

logger = logging.getLogger(__name__)


class BotErrorPresenter:
    """Контекстный менеджер: доменную/прикладную ошибку превращает в понятный ответ.

    Хендлеры бота пишутся как «счастливый путь» внутри ``async with presented(...)``,
    а выбор текста по коду ошибки — табличная стратегия, а не цепочка ``if``.
    Непредвиденные исключения не глотаются: их увидит middleware логирования aiogram.
    """

    def __init__(self, texts: Mapping[str, str], fallback: str) -> None:
        """Задать тексты по кодам ошибок и запасной текст."""
        self._texts = texts
        self._fallback = fallback

    @asynccontextmanager
    async def presented(self, target: Message | CallbackQuery) -> AsyncIterator[None]:
        """Выполнить блок, отвечая пользователю при ожидаемой ошибке."""
        try:
            yield
        except (DomainError, ApplicationError) as error:
            logger.info("Бот: %s (%s)", error.code, error)
            await self._reply(target, self._texts.get(error.code, self._fallback))

    @staticmethod
    async def _reply(target: Message | CallbackQuery, text: str) -> None:
        """Ответить в чат (для callback — ещё и закрыть «часики»)."""
        if isinstance(target, CallbackQuery):
            await target.answer()
            if isinstance(target.message, Message):
                await target.message.answer(text)
            return
        await target.answer(text)
