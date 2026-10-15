"""Спецификации контекста Identity."""

from __future__ import annotations

from beauty.contexts.identity.domain.value_objects import TelegramContact
from beauty.shared.domain.specification import Specification


class ContactOwnedBySender(Specification[TelegramContact]):
    """Контакт принадлежит тому, кто его прислал.

    Кнопка ``request_contact`` отправляет собственный контакт пользователя, но в
    чат можно переслать и чужой контакт из записной книжки. Без этой проверки любой
    вошёл бы под чужим номером: достаточно прислать карточку жертвы.
    """

    def is_satisfied_by(self, candidate: TelegramContact) -> bool:
        """``contact.user_id`` совпадает с id отправителя."""
        return candidate.contact_user_id is not None and candidate.contact_user_id == candidate.sender.value


class ContactHasPhone(Specification[TelegramContact]):
    """В контакте есть номер телефона."""

    def is_satisfied_by(self, candidate: TelegramContact) -> bool:
        """Номер не пустой."""
        return bool(candidate.phone_raw.strip())
