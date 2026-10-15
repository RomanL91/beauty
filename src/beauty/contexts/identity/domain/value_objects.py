"""Value objects контекста Identity."""

from __future__ import annotations

import re
from dataclasses import dataclass

from beauty.contexts.identity.domain.errors import (
    InvalidAuthNonce,
    InvalidConfirmationCode,
    InvalidPhoneNumber,
    InvalidTelegramUserId,
)

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_NOISE = re.compile(r"[\s\-().]")
_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_CODE = re.compile(r"^\d{2}$")


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """Номер телефона в формате E.164 (``+77011234567``)."""

    value: str

    def __post_init__(self) -> None:
        """Проверить формат."""
        if not _E164.match(self.value):
            raise InvalidPhoneNumber(f"Некорректный номер: {self.value!r}")

    @classmethod
    def from_raw(cls, raw: str) -> PhoneNumber:
        """Нормализовать номер из Telegram или пользовательского ввода.

        Telegram отдаёт номер без ``+`` (``77011234567``); локальный формат
        ``8XXXXXXXXXX`` для Казахстана и России приводится к ``+7XXXXXXXXXX``.
        """
        digits = _NOISE.sub("", raw.strip())
        if digits.startswith("+"):
            return cls(digits)
        if len(digits) == 11 and digits.startswith("8"):
            return cls(f"+7{digits[1:]}")
        return cls(f"+{digits}")

    def ends_with(self, suffix: str) -> bool:
        """Совпадают ли последние цифры (поиск «Дарья, телефон на 8967»)."""
        return bool(suffix) and self.value.endswith(suffix)

    def masked(self) -> str:
        """Номер для показа: видны код страны и последние четыре цифры."""
        return f"{self.value[:2]}•••••{self.value[-4:]}"


@dataclass(frozen=True, slots=True)
class TelegramUserId:
    """Идентификатор пользователя Telegram."""

    value: int

    def __post_init__(self) -> None:
        """Проверить, что id положительный."""
        if self.value <= 0:
            raise InvalidTelegramUserId(f"Некорректный Telegram id: {self.value}")


@dataclass(frozen=True, slots=True)
class ConfirmationCode:
    """Двузначный код сверки браузера и Telegram (number matching)."""

    value: str

    def __post_init__(self) -> None:
        """Проверить формат."""
        if not _CODE.match(self.value):
            raise InvalidConfirmationCode(f"Некорректный код: {self.value!r}")


@dataclass(frozen=True, slots=True)
class AuthNonce:
    """Одноразовый токен входа, передаваемый боту через deep link ``?start=``.

    Telegram допускает в параметре ``start`` до 64 символов ``[A-Za-z0-9_-]``.
    """

    value: str

    def __post_init__(self) -> None:
        """Проверить формат."""
        if not _NONCE.match(self.value):
            raise InvalidAuthNonce("Некорректный токен входа")


@dataclass(frozen=True, slots=True)
class TelegramContact:
    """Контакт, присланный в бот кнопкой «Поделиться контактом».

    Атрибуты:
        sender: кто прислал сообщение.
        contact_user_id: чей это контакт по данным Telegram (``None`` — контакт из
            записной книжки без аккаунта Telegram).
        phone_raw: номер в том виде, как его прислал Telegram.
    """

    sender: TelegramUserId
    contact_user_id: int | None
    phone_raw: str
