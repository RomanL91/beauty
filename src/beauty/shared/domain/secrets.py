"""Хранение высокоэнтропийных секретов в виде хеша.

Секреты (секрет браузера в auth-challenge, refresh-токен) генерируются как 256 бит
случайности, поэтому для них достаточно SHA-256: перебор такого пространства
невозможен, и медленные KDF (argon2/bcrypt), нужные для паролей, здесь лишние.
Сравнение — только через ``hmac.compare_digest``, чтобы не давать timing-оракул.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HashedSecret:
    """Value object: hex-дайджест SHA-256 секрета."""

    digest: str

    @classmethod
    def of(cls, raw_secret: str) -> HashedSecret:
        """Посчитать хеш секрета."""
        return cls(hashlib.sha256(raw_secret.encode("utf-8")).hexdigest())

    def matches(self, raw_secret: str) -> bool:
        """Проверить секрет за постоянное время."""
        candidate = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate, self.digest)
