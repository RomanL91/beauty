"""Хендлеры бота авторизации."""

from __future__ import annotations

from collections.abc import Mapping

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup

from beauty.contexts.identity.application.commands import (
    ClaimChallenge,
    CompleteChallengeWithContact,
    ConfirmChallengeCode,
)
from beauty.contexts.identity.presentation.bot.errors import BotErrorPresenter
from beauty.contexts.identity.presentation.bot.keyboards import AuthKeyboards, ConfirmCodeCallback
from beauty.contexts.identity.presentation.bot.renderers import ClaimStepRenderers
from beauty.contexts.identity.presentation.bot.texts import BotTexts
from beauty.shared.application.mediator import Mediator


class TelegramAuthBotController:
    """Сценарий входа в боте: deep link → код сверки → контакт.

    Все решения принимает прикладной слой; контроллер лишь извлекает данные из
    апдейта Telegram, отправляет команду и показывает результат.
    """

    def __init__(
        self,
        mediator: Mediator,
        keyboards: AuthKeyboards,
        renderers: ClaimStepRenderers,
        errors: BotErrorPresenter,
    ) -> None:
        """Получить зависимости."""
        self._mediator = mediator
        self._keyboards = keyboards
        self._renderers = renderers
        self._errors = errors
        self._code_outcomes: Mapping[bool, tuple[str, ReplyKeyboardMarkup | None]] = {
            True: (BotTexts.SHARE_CONTACT, keyboards.request_contact()),
            False: (BotTexts.CODE_REJECTED, None),
        }
        self._contact_greetings: Mapping[bool, str] = {
            True: BotTexts.CONTACT_ACCEPTED_NEW,
            False: BotTexts.CONTACT_ACCEPTED,
        }

    def router(self) -> Router:
        """Роутер aiogram с хендлерами входа."""
        router = Router(name="identity-auth")
        router.message.register(self.on_start_with_payload, CommandStart(deep_link=True))
        router.message.register(self.on_start, CommandStart())
        router.callback_query.register(self.on_code_chosen, ConfirmCodeCallback.filter())
        router.message.register(self.on_contact, F.contact)
        return router

    async def on_start(self, message: Message) -> None:
        """``/start`` без параметра — объяснить, как войти."""
        await message.answer(BotTexts.GREETING)

    async def on_start_with_payload(self, message: Message, command: CommandObject) -> None:
        """Пользователь пришёл по deep link из PWA."""
        if message.from_user is None or not command.args:
            await message.answer(BotTexts.GREETING)
            return
        nonce = command.args
        async with self._errors.presented(message):
            result = await self._mediator.send(
                ClaimChallenge(nonce=nonce, telegram_user_id=message.from_user.id)
            )
            await self._renderers.for_step(result.step).render(message, nonce, result)

    async def on_code_chosen(self, query: CallbackQuery, callback_data: ConfirmCodeCallback) -> None:
        """Пользователь выбрал код сверки."""
        async with self._errors.presented(query):
            result = await self._mediator.send(
                ConfirmChallengeCode(
                    nonce=callback_data.nonce, telegram_user_id=query.from_user.id, code=callback_data.code
                )
            )
            await query.answer()
            if isinstance(query.message, Message):
                await query.message.edit_reply_markup(reply_markup=None)
                text, markup = self._code_outcomes[result.accepted]
                await query.message.answer(text, reply_markup=markup)

    async def on_contact(self, message: Message) -> None:
        """Пользователь поделился контактом."""
        if message.from_user is None or message.contact is None:
            return
        async with self._errors.presented(message):
            accepted = await self._mediator.send(
                CompleteChallengeWithContact(
                    sender_telegram_user_id=message.from_user.id,
                    contact_user_id=message.contact.user_id,
                    phone=message.contact.phone_number,
                )
            )
            template = self._contact_greetings[accepted.is_new_client]
            await message.answer(
                template.format(phone=accepted.masked_phone), reply_markup=self._keyboards.remove()
            )
