"""Показ телефона клиента мастеру: маска и имя «Новый клиент · …89 67»."""

from __future__ import annotations


def masked_phone(e164: str) -> str:
    """``+77051238967`` → ``+7 705 ••• 89 67`` (видны код страны, оператор и 4 цифры)."""
    digits = e164.removeprefix("+")
    tail = f"{digits[-4:-2]} {digits[-2:]}"
    if e164.startswith("+7") and len(digits) == 11:
        return f"+7 {digits[1:4]} ••• {tail}"
    return f"+{digits[:-7]} ••• {tail}"


def anonymous_name(e164: str) -> str:
    """Подпись клиента без имени: ``Новый клиент · …89 67``."""
    digits = e164.removeprefix("+")
    return f"Новый клиент · …{digits[-4:-2]} {digits[-2:]}"


def anonymous_from_mask(masked: str) -> str:
    """Та же подпись по маске ``+7 705 ••• 89 67`` (когда полного номера под рукой нет)."""
    return f"Новый клиент · …{masked[-5:]}"
