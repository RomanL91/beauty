"""Web Push: шифрование RFC 8291 (aes128gcm), VAPID RFC 8292, отправка через httpx."""

from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import http_ece
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02

from beauty.contexts.notifications.application.ports import PushPayload, PushSender, PushTarget, SendOutcome

logger = logging.getLogger(__name__)

GONE_STATUSES = frozenset({404, 410})
VAPID_LIFETIME = 12 * 3600


def b64url_decode(value: str) -> bytes:
    """base64url без выравнивания → байты."""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64url_encode(value: bytes) -> str:
    """Байты → base64url без выравнивания."""
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


@dataclass(frozen=True, slots=True)
class VapidKeys:
    """Пара ключей VAPID: закрытый — 32 байта (base64url), открытый — точка P-256 (base64url)."""

    private_key: str
    public_key: str

    @classmethod
    def generate(cls) -> VapidKeys:
        """Новая пара (``beauty push keys``)."""
        key = ec.generate_private_key(ec.SECP256R1())
        raw = key.private_numbers().private_value.to_bytes(32, "big")
        point = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return cls(b64url_encode(raw), b64url_encode(point))


def encrypt(payload: bytes, target: PushTarget) -> bytes:
    """Тело сообщения, зашифрованное ключами подписки (RFC 8291, aes128gcm)."""
    server_key = ec.generate_private_key(ec.SECP256R1())
    return bytes(
        http_ece.encrypt(
            payload,
            salt=os.urandom(16),
            private_key=server_key,
            dh=b64url_decode(target.p256dh),
            auth_secret=b64url_decode(target.auth),
            version="aes128gcm",
        )
    )


class WebPushSender(PushSender):
    """Отправка на push-сервис устройства с подписью VAPID."""

    def __init__(self, http: httpx.AsyncClient, keys: VapidKeys, subject: str, ttl: int = 86_400) -> None:
        """Ключи VAPID, контакт отправителя (``mailto:``) и срок хранения сообщения у push-сервиса."""
        self._http = http
        self._vapid = Vapid02.from_raw(keys.private_key.encode())
        self._subject = subject
        self._ttl = ttl

    async def send(self, target: PushTarget, payload: PushPayload) -> SendOutcome:
        """Зашифровать, подписать и отправить."""
        try:
            body = encrypt(payload.to_json(), target)
        except (ValueError, TypeError) as error:
            logger.warning("Подписка с битыми ключами: %s", error)
            return SendOutcome.GONE
        parts = urlsplit(target.endpoint)
        claims = {
            "sub": self._subject,
            "aud": f"{parts.scheme}://{parts.netloc}",
            "exp": int(time.time()) + VAPID_LIFETIME,
        }
        headers = {
            **self._vapid.sign(claims),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(self._ttl),
            "Urgency": "high" if payload.kind in ("message", "reminder") else "normal",
        }
        try:
            response = await self._http.post(target.endpoint, content=body, headers=headers)
        except httpx.HTTPError as error:
            logger.warning("Push-сервис недоступен: %s", error)
            return SendOutcome.FAILED
        if response.status_code in GONE_STATUSES:
            return SendOutcome.GONE
        if response.is_success:
            return SendOutcome.SENT
        logger.warning("Push-сервис ответил %s: %s", response.status_code, response.text[:200])
        return SendOutcome.FAILED


class DisabledPushSender(PushSender):
    """Ключей VAPID нет — уведомления не отправляются (только в журнал)."""

    async def send(self, target: PushTarget, payload: PushPayload) -> SendOutcome:
        """Записать в журнал."""
        logger.info("Push выключен (нет ключей VAPID): %s — %s", payload.kind, payload.title)
        return SendOutcome.FAILED
