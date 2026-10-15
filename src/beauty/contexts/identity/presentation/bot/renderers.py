"""Отрисовка следующего шага входа (Strategy по ``ClaimStep``)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from aiogram.types import Message

from beauty.contexts.identity.application.dto import ClaimResult, ClaimStep
from beauty.contexts.identity.presentation.bot.keyboards import AuthKeyboards
from beauty.contexts.identity.presentation.bot.texts import BotTexts


class ClaimStepRenderer(ABC):
    """Показывает пользователю шаг входа."""

    def __init__(self, keyboards: AuthKeyboards) -> None:
        """Получить фабрику клавиатур."""
        self._keyboards = keyboards

    @abstractmethod
    async def render(self, message: Message, nonce: str, result: ClaimResult) -> None:
        """Отправить сообщение с шагом."""


class AskCodeRenderer(ClaimStepRenderer):
    """Просит выбрать код с экрана браузера."""

    async def render(self, message: Message, nonce: str, result: ClaimResult) -> None:
        """Варианты кода инлайн-кнопками."""
        await message.answer(
            BotTexts.CHOOSE_CODE, reply_markup=self._keyboards.code_options(nonce, result.code_options)
        )


class AskContactRenderer(ClaimStepRenderer):
    """Просит поделиться контактом."""

    async def render(self, message: Message, nonce: str, result: ClaimResult) -> None:
        """Кнопка «Поделиться контактом»."""
        await message.answer(BotTexts.SHARE_CONTACT, reply_markup=self._keyboards.request_contact())


class ClaimStepRenderers:
    """Реестр стратегий отрисовки."""

    def __init__(self, keyboards: AuthKeyboards) -> None:
        """Зарегистрировать отрисовщики всех шагов."""
        self._renderers: Mapping[ClaimStep, ClaimStepRenderer] = {
            ClaimStep.ASK_CODE: AskCodeRenderer(keyboards),
            ClaimStep.ASK_CONTACT: AskContactRenderer(keyboards),
        }

    def for_step(self, step: ClaimStep) -> ClaimStepRenderer:
        """Отрисовщик шага."""
        return self._renderers[step]
