"""Push-уведомления на реальном PostgreSQL: подписки через API, уведомления по событиям,
напоминание о визите задачей планировщика.

Push-сервис браузера заменён «записывающим» отправителем: шифрование и VAPID проверены
unit-тестами, здесь — кому и что уходит.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, text

from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DEMO_SLUG, DemoMasterSeeder
from beauty.contexts.conversations.application.commands import HandOffToMaster
from beauty.contexts.notifications.application.notify import NotifyAbout
from beauty.contexts.notifications.application.ports import PushPayload, PushSender, PushTarget, SendOutcome
from beauty.contexts.notifications.infrastructure.tables import push_subscriptions
from beauty.entrypoints.api import ApiApplicationFactory
from beauty.shared.infrastructure.messaging.handler import IntegrationEventHandler
from beauty.shared.infrastructure.outbox.envelope import EventEnvelope
from beauty.shared.infrastructure.scheduling.poller import ScheduledJobPoller
from tests.integration.helpers import EventPump, login
from tests.integration.test_booking import BASE, Client, free_slot, new_client, service_id

pytestmark = pytest.mark.integration

API = "/api/v1"
OWNER_PHONE = "+77010009001"


@pytest.fixture(scope="session")
def app(container: ApplicationContainer) -> FastAPI:
    """Приложение без realtime-моста."""
    return ApiApplicationFactory(container, enable_realtime_bridge=False).create()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP-клиент поверх ASGI."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        yield client


@pytest.fixture
async def master(http: httpx.AsyncClient, container: ApplicationContainer) -> dict[str, str]:
    """Демо-мастер; заголовки его кабинета."""
    await DemoMasterSeeder(container.mediator).seed(OWNER_PHONE)
    token = await login(http, container.mediator, 9001, OWNER_PHONE[1:])
    return {"Authorization": f"Bearer {token}"}


class RecordingSender(PushSender):
    """Push-сервис браузеров: запоминает доставленное; ``gone`` — исчезнувшие подписки."""

    def __init__(self) -> None:
        """Пусто."""
        self.sent: list[tuple[str, PushPayload]] = []
        self.gone: set[str] = set()

    async def send(self, target: PushTarget, payload: PushPayload) -> SendOutcome:
        """Запомнить."""
        if target.endpoint in self.gone:
            return SendOutcome.GONE
        self.sent.append((target.endpoint, payload))
        return SendOutcome.SENT

    def to(self, endpoint: str) -> list[tuple[str, str]]:
        """(kind, title) уведомлений устройства."""
        return [(p.kind, p.title) for e, p in self.sent if e == endpoint]


class RecordingPushConsumer(IntegrationEventHandler):
    """Консьюмер уведомлений, как в worker, но с записывающим отправителем."""

    def __init__(self, container: ApplicationContainer, sender: PushSender) -> None:
        """Обработчик уведомлений контейнера с подменённым отправителем."""
        self._handler = container.notifications.notify_handler(sender)

    async def handle(self, envelope: EventEnvelope) -> None:
        """Уведомить."""
        await self._handler.handle(NotifyAbout(envelope.routing_key, dict(envelope.payload)))


def device(name: str) -> str:
    """Endpoint устройства у push-сервиса."""
    return f"https://push.example.com/send/{name}-{uuid4().hex[:8]}"


async def subscribe(
    http: httpx.AsyncClient, headers: dict[str, str], endpoint: str, app: str = "client", **extra: Any
) -> httpx.Response:
    """Подписать устройство."""
    body = {"app": app, "endpoint": endpoint, "keys": {"p256dh": "BPkey", "auth": "auth"}, **extra}
    if app == "client":
        body.setdefault("master_slug", DEMO_SLUG)
    return await http.post(f"{API}/push/subscriptions", json=body, headers=headers)


async def test_subscription_api(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Подписка: повтор endpoint — та же; без страницы — 422; кабинет — только владельцу; чужую не удалить."""
    client = await new_client(http, container, 9011)
    phone = device("phone")
    first = await subscribe(http, client.headers, phone)
    assert first.status_code == 201, first.text
    again = await subscribe(http, client.headers, phone, expiration_time=1_900_000_000_000)
    assert again.json()["id"] == first.json()["id"]
    unknown = await subscribe(http, client.headers, device("x"), master_slug="nobody")
    assert (unknown.status_code, unknown.json()["code"]) == (422, "unknown_master_page")
    not_master = await subscribe(http, client.headers, device("x"), app="master")
    assert (not_master.status_code, not_master.json()["code"]) == (403, "not_a_master")
    cabinet = await subscribe(http, master, device("laptop"), app="master")
    assert cabinet.status_code == 201, cabinet.text
    bad = await subscribe(http, client.headers, "http://insecure.example.com/x")
    assert (bad.status_code, bad.json()["code"]) == (422, "invalid_push_subscription")

    foreign = await http.delete(f"{API}/push/subscriptions/{first.json()['id']}", headers=master)
    assert (foreign.status_code, foreign.json()["code"]) == (404, "push_subscription_not_found")
    own = await http.delete(f"{API}/push/subscriptions/{first.json()['id']}", headers=client.headers)
    assert own.status_code == 204
    assert (await http.post(f"{API}/push/subscriptions", json={"app": "client"})).status_code == 401


async def test_booking_flow_notifies_both_sides_and_reminds(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Заявка → мастеру; подтверждение → клиенту; задача планировщика → напоминание в чате и push."""
    sender = RecordingSender()
    pump = EventPump(container, {"notifications.push": RecordingPushConsumer(container, sender)})
    client = await new_client(http, container, 9021)
    phone, laptop = device("phone"), device("laptop")
    assert (await subscribe(http, client.headers, phone)).status_code == 201
    assert (await subscribe(http, master, laptop, app="master")).status_code == 201

    service = await service_id(http)
    slot = await free_slot(http, service)
    await client.send({"kind": "book_slot", "service_id": service, "start": slot["start"]})
    await pump.drain()
    assert sender.to(laptop) == [("appointment_requested", "Новая заявка")]
    card = (await client.history())[-1]["appointment"]

    confirmed = await http.post(f"{API}/me/appointments/{card['id']}/confirm", headers=master)
    assert confirmed.status_code == 200, confirmed.text
    await pump.drain()
    assert sender.to(phone) == [("appointment_confirmed", "Алиса")]

    async with container.engine.begin() as connection:
        due = await connection.execute(
            text("UPDATE infra.scheduled_jobs SET due_at = now() - interval '1 minute' WHERE kind = :kind"),
            {"kind": "booking.remind_visit"},
        )
        assert due.rowcount == 1
    poller = ScheduledJobPoller(container.session_factory, container.job_handlers, container.clock)
    assert await poller.tick() == 1
    await pump.drain()
    history = await client.history()
    assert history[-1]["text"].startswith("Напоминаем:")
    assert history[1]["appointment"]["reminder"] == "sent"
    assert sender.to(phone)[-1] == ("reminder", "Алиса")
    assert all(kind != "message" for kind, _ in sender.to(phone))  # системные строки — без лишних push


async def test_messages_and_gone_devices(
    http: httpx.AsyncClient, container: ApplicationContainer, master: dict[str, str]
) -> None:
    """Агент передал вопрос → мастеру; ответ мастера → клиенту; исчезнувшее устройство удаляется."""
    sender = RecordingSender()
    pump = EventPump(container, {"notifications.push": RecordingPushConsumer(container, sender)})
    client: Client = await new_client(http, container, 9031)
    phone, old_phone, laptop = device("phone"), device("old"), device("laptop")
    for endpoint in (phone, old_phone):
        assert (await subscribe(http, client.headers, endpoint)).status_code == 201
    assert (await subscribe(http, master, laptop, app="master")).status_code == 201
    sender.gone.add(old_phone)

    await client.send({"kind": "text", "text": "Есть парковка?"})
    await container.mediator.send(
        HandOffToMaster(UUID(client.conversation_id), "Агент передал вам: парковка")
    )
    await pump.drain()
    assert sender.to(laptop) == [("message", "Нужен ваш ответ")]

    reply = {"client_id": str(uuid4()), "kind": "text", "text": "Да, во дворе."}
    path = f"{API}/me/conversations/{client.conversation_id}/messages"
    assert (await http.post(path, json=reply, headers=master)).status_code == 201
    await pump.drain()
    assert sender.to(phone) == [("message", "Алиса")]
    assert sender.sent[-1][1].body == "Да, во дворе."

    await client.send({"kind": "text", "text": "Спасибо!"})  # диалог теперь ведёт мастер
    await pump.drain()
    assert sender.to(laptop)[-1][0] == "message"
    assert sender.to(laptop)[-1][1].startswith("Новый клиент")
    async with container.engine.connect() as connection:
        left = await connection.scalar(
            select(func.count())
            .select_from(push_subscriptions)
            .where(push_subscriptions.c.endpoint == old_phone)
        )
    assert left == 0
