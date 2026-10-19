"""Пароли администраторов: scrypt с солью (стандартная библиотека, без зависимостей).

Формат хеша: ``scrypt$<n>$<r>$<p>$<соль base64>$<ключ base64>`` — параметры хранятся
рядом, поэтому их можно усилить позже, не ломая старые пароли. Проверка — за
постоянное время.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from beauty.contexts.admin.domain.errors import WeakPassword

MIN_LENGTH = 10
MAX_LENGTH = 200
_N, _R, _P, _KEY = 2**14, 8, 1, 32


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=_KEY, maxmem=64 * 1024 * 1024)


def check_strength(password: str) -> None:
    """Новый пароль: от 10 до 200 символов, не только пробелы."""
    if not MIN_LENGTH <= len(password) <= MAX_LENGTH or not password.strip():
        raise WeakPassword(f"Пароль — от {MIN_LENGTH} до {MAX_LENGTH} символов")


def hash_password(password: str) -> str:
    """Хеш нового пароля (длина проверяется)."""
    check_strength(password)
    salt = secrets.token_bytes(16)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(_derive(password, salt, _N, _R, _P))}"


def verify_password(password: str, encoded: str) -> bool:
    """Совпадает ли пароль с хешем (испорченный хеш — ``False``)."""
    try:
        scheme, n, r, p, salt, key = encoded.split("$")
        if scheme != "scrypt" or len(password) > MAX_LENGTH:
            return False
        derived = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, base64.b64decode(key))


DUMMY_HASH = "scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA==$" + _b64(bytes(_KEY))
"""Хеш для неизвестного логина: проверка идёт так же долго, логин не угадать по времени."""
