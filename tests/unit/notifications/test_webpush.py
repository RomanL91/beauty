"""Web Push: шифрование, которое расшифровывает только подписка, и подпись VAPID."""

from __future__ import annotations

import json
import os
from typing import Any

import http_ece
import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from beauty.contexts.notifications.application.ports import PushPayload, PushTarget, SendOutcome
from beauty.contexts.notifications.infrastructure.webpush import (
    VapidKeys,
    WebPushSender,
    b64url_decode,
    b64url_encode,
)

PAYLOAD = PushPayload("reminder", "Алиса", "Напоминаем: завтра в 12:00 — массаж", "/chat", "appointment-1")


class Browser:
    """Подписка браузера: свои ключи (как у ``pushManager.subscribe``)."""

    def __init__(self) -> None:
        """Ключи P-256 и секрет auth."""
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        point = self.key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.target = PushTarget(
            "https://push.example.com/send/abc", b64url_encode(point), b64url_encode(self.auth)
        )

    def decrypt(self, body: bytes) -> dict[str, Any]:
        """Расшифровать, как браузер."""
        plain = http_ece.decrypt(body, private_key=self.key, auth_secret=self.auth, version="aes128gcm")
        decoded: dict[str, Any] = json.loads(plain)
        return decoded


def push_service(status: int, seen: list[httpx.Request]) -> httpx.AsyncClient:
    """Push-сервис браузера, отвечающий ``status``."""

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


async def test_payload_is_encrypted_for_the_subscription_and_signed() -> None:
    """Тело расшифровывает только подписка; JWT VAPID — для origin push-сервиса, подпись верна."""
    browser, seen = Browser(), []
    keys = VapidKeys.generate()
    sender = WebPushSender(push_service(201, seen), keys, "mailto:admin@beautiful.kz", ttl=3600)
    assert await sender.send(browser.target, PAYLOAD) is SendOutcome.SENT
    (request,) = seen
    assert browser.decrypt(request.content) == {
        "kind": "reminder",
        "title": "Алиса",
        "body": "Напоминаем: завтра в 12:00 — массаж",
        "url": "/chat",
        "tag": "appointment-1",
    }
    assert (request.headers["Content-Encoding"], request.headers["TTL"]) == ("aes128gcm", "3600")
    token, key = request.headers["Authorization"].removeprefix("vapid ").split(",")
    assert key == f"k={keys.public_key}"
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64url_decode(keys.public_key))
    claims = jwt.decode(
        token.removeprefix("t="), public, algorithms=["ES256"], audience="https://push.example.com"
    )
    assert claims["sub"] == "mailto:admin@beautiful.kz"


async def test_gone_and_failed_subscriptions() -> None:
    """404/410 — подписки нет; 5xx — временная ошибка."""
    browser, keys = Browser(), VapidKeys.generate()
    for status, outcome in ((410, SendOutcome.GONE), (404, SendOutcome.GONE), (503, SendOutcome.FAILED)):
        sender = WebPushSender(push_service(status, []), keys, "mailto:a@b.kz")
        assert await sender.send(browser.target, PAYLOAD) is outcome
