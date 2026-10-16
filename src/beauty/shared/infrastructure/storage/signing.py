"""Подписанные ссылки на файлы хранилища.

``<audio src>`` не умеет слать ``Authorization``, поэтому доступ к медиа даёт сама
ссылка: HMAC от ключа и срока действия. Срок округляется вверх до шага — ссылка на
один файл стабильна в пределах шага, и браузер с service worker её кэшируют.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
from datetime import timedelta
from urllib.parse import quote

from beauty.shared.domain.clock import Clock


class SignedMediaUrls:
    """Выдаёт и проверяет ссылки ``<prefix>/media/<key>?exp=<unix>&sig=<hmac>``."""

    def __init__(
        self,
        secret: str,
        prefix: str,
        clock: Clock,
        ttl: timedelta = timedelta(hours=1),
        step: timedelta = timedelta(minutes=10),
    ) -> None:
        """Задать ключ подписи, префикс API, часы и сроки."""
        self._secret = hashlib.sha256(b"media:" + secret.encode()).digest()
        self._prefix = prefix.rstrip("/")
        self._clock = clock
        self._ttl = ttl
        self._step = int(step.total_seconds())

    def url(self, key: str) -> str:
        """Подписанная ссылка на файл."""
        horizon = (self._clock.now() + self._ttl).timestamp()
        expires = math.ceil(horizon / self._step) * self._step
        return f"{self._prefix}/media/{quote(key)}?exp={expires}&sig={self._sign(key, expires)}"

    def verify(self, key: str, expires: int, signature: str) -> bool:
        """Подпись верна и срок не истёк."""
        if expires < self._clock.now().timestamp():
            return False
        return hmac.compare_digest(self._sign(key, expires), signature)

    def _sign(self, key: str, expires: int) -> str:
        digest = hmac.new(self._secret, f"{key}\n{expires}".encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest[:24]).decode().rstrip("=")
