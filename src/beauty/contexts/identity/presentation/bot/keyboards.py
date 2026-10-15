"""Клавиатуры и callback-данные бота."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from beauty.contexts.identity.presentation.bot.texts import BotTexts


class ConfirmCodeCallback(CallbackData, prefix="ac"):
    """Выбор кода сверки: ``ac:<nonce>:<code>`` (укладывается в лимит Telegram 64 байта)."""

    nonce: str
    code: str


class AuthKeyboards:
    """Фабрика клавиатур."""

    def code_options(self, nonce: str, codes: Sequence[str]) -> InlineKeyboardMarkup:
        """Кнопки с вариантами кода в один ряд."""
        builder = InlineKeyboardBuilder()
        for code in codes:
            builder.button(text=code, callback_data=ConfirmCodeCallback(nonce=nonce, code=code))
        builder.adjust(len(codes))
        return builder.as_markup()

    def request_contact(self) -> ReplyKeyboardMarkup:
        """Кнопка «Поделиться контактом» (Telegram пришлёт собственный контакт пользователя)."""
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BotTexts.SHARE_CONTACT_BUTTON, request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
            is_persistent=False,
        )

    def remove(self) -> ReplyKeyboardRemove:
        """Убрать reply-клавиатуру."""
        return ReplyKeyboardRemove()
