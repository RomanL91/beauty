"""Запись и переписка на реальном PostgreSQL: HTTP API, события, поток, ограничения БД."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from beauty.bootstrap.container import ApplicationContainer
from beauty.bootstrap.demo import DEMO_SLUG, DemoMasterSeeder
from beauty.contexts.booking.application.commands import ConfirmAppointment, DeclineAppointment
from beauty.contexts.booking.application.errors import SlotTakenError
from beauty.contexts.booking.domain.appointment import Appointment
from beauty.contexts.booking.domain.value_objects import ClientSnapshot, ServiceSnapshot, TimeSlot
from beauty.contexts.booking.infrastructure.uow import SqlAlchemyBookingUnitOfWork
from beauty.entrypoints.api import ApiApplicationFactory
from beauty.shared.infrastructure.scheduling.poller import ScheduledJobPoller
from tests.integration.contract import assert_matches_schema
from tests.integration.helpers import EventPump, login

pytestmark = pytest.mark.integration

BASE = "https://alisa.beautiful.kz"
API = "/api/v1"


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
async def master_id(container: ApplicationContainer) -> UUID:
    """Опубликованный демо-мастер."""
    return await DemoMasterSeeder(container.mediator).seed()


@pytest.fixture
def pump(container: ApplicationContainer) -> EventPump:
    """Доставка событий outbox консьюмерам."""
    return EventPump(container)


class Client:
    """Клиент PWA: свой токен и своя переписка."""

    def __init__(self, http: httpx.AsyncClient, token: str) -> None:
        """Запомнить клиента."""
        self.http = http
        self.headers = {"Authorization": f"Bearer {token}"}
        self.conversation_id = ""

    async def open(self) -> httpx.Response:
        """Открыть переписку с демо-мастером."""
        response = await self.http.post(
            f"{API}/conversations/me", params={"master": DEMO_SLUG}, headers=self.headers
        )
        self.conversation_id = response.json().get("id", "")
        return response

    async def send(self, body: dict[str, Any]) -> httpx.Response:
        """Отправить сообщение (``client_id`` — новый, если не задан)."""
        payload = {"client_id": str(uuid4()), **body}
        return await self.http.post(
            f"{API}/conversations/{self.conversation_id}/messages", json=payload, headers=self.headers
        )

    async def history(self) -> list[dict[str, Any]]:
        """Вся история (проверенная по контракту)."""
        response = await self.http.get(
            f"{API}/conversations/{self.conversation_id}/messages",
            params={"limit": 100},
            headers=self.headers,
        )
        assert response.status_code == 200, response.text
        assert_matches_schema(response.json(), "MessagePage")
        items: list[dict[str, Any]] = response.json()["items"]
        return items

    async def events(self, last_event_id: str | None = None) -> list[dict[str, Any]]:
        """Кадры SSE-потока (поток в тестах живёт доли секунды)."""
        headers = dict(self.headers)
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
        response = await self.http.get(f"{API}/conversations/{self.conversation_id}/events", headers=headers)
        assert response.status_code == 200, response.text
        return parse_sse(response.text)


def parse_sse(body: str) -> list[dict[str, Any]]:
    """Кадры с данными: ``{"id", "event", "data"}``."""
    frames = []
    for block in body.split("\n\n"):
        fields: dict[str, Any] = {}
        for line in block.splitlines():
            name, _, value = line.partition(": ")
            if name in ("id", "event"):
                fields[name] = value
            elif name == "data":
                fields["data"] = json.loads(value)
        if "data" in fields:
            frames.append(fields)
    return frames


async def new_client(http: httpx.AsyncClient, container: ApplicationContainer, user: int) -> Client:
    """Войти и открыть переписку."""
    token = await login(http, container.mediator, user, f"7701555{user:04d}")
    client = Client(http, token)
    assert (await client.open()).status_code == 201
    return client


async def free_slot(http: httpx.AsyncClient, service_id: str, days_ahead: int = 2) -> dict[str, Any]:
    """Первое свободное окно не раньше чем через ``days_ahead`` дней (дедлайн переноса — 12 ч)."""
    since = (datetime.now(UTC) + timedelta(days=days_ahead)).isoformat()
    response = await http.get(
        f"{API}/masters/{DEMO_SLUG}/slots", params={"service": service_id, "from": since, "limit": 5}
    )
    slots: list[dict[str, Any]] = response.json()["items"]
    return slots[0]


async def service_id(http: httpx.AsyncClient) -> str:
    """Услуга на 60 минут демо-мастера."""
    page = (await http.get(f"{API}/masters/{DEMO_SLUG}")).json()
    return str(next(s["id"] for s in page["services"] if s["duration_min"] == 60))


async def test_book_in_chat_confirm_and_cancel(
    http: httpx.AsyncClient, container: ApplicationContainer, master_id: UUID, pump: EventPump
) -> None:
    """book_slot → карточка заявки → мастер подтверждает → клиент отменяет; окна учитывают запись."""
    client = await new_client(http, container, 5001)
    again = await client.open()
    assert again.status_code == 200
    assert again.json() == {"id": client.conversation_id, "master_slug": DEMO_SLUG}
    found = await http.get(f"{API}/conversations/me", params={"master": DEMO_SLUG}, headers=client.headers)
    assert found.json()["id"] == client.conversation_id

    service = await service_id(http)
    slot = await free_slot(http, service)
    request = {"client_id": str(uuid4()), "kind": "book_slot", "service_id": service, "start": slot["start"]}
    sent = await client.send(request)
    assert sent.status_code == 201, sent.text
    assert_matches_schema(sent.json(), "Message")
    assert sent.json()["text"].startswith("Хочу записаться: ")
    repeated = await client.send(request)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == sent.json()["id"]

    delivered = await pump.drain()
    assert "conversations.client.message_posted" in delivered
    assert "booking.appointment.requested" in delivered
    history = await client.history()
    assert [m["kind"] for m in history] == ["text", "booking_card"]
    card = history[1]
    assert card["author"] == "agent"
    appointment = card["appointment"]
    assert appointment["status"] == "requested"
    assert appointment["start"] == slot["start"]
    assert appointment["client"]["display_name"].startswith("Новый клиент · …")
    assert appointment["hold_until"] == appointment["auto_decline_at"]

    slots_after = await http.get(
        f"{API}/masters/{DEMO_SLUG}/slots", params={"service": service, "from": slot["start"], "limit": 1}
    )
    assert slots_after.json()["items"][0]["start"] != slot["start"]

    await container.mediator.send(ConfirmAppointment(UUID(appointment["id"])))
    await pump.drain()
    history = await client.history()
    assert history[1]["appointment"]["status"] == "confirmed"
    assert history[-1]["kind"] == "system"
    assert history[-1]["tone"] == "success"
    assert history[-1]["text"].startswith("Запись подтверждена: ")

    stranger = Client(http, await login(http, container.mediator, 5002, "77015550202"))
    foreign = await stranger.http.post(
        f"{API}/appointments/{appointment['id']}/cancel", json={}, headers=stranger.headers
    )
    assert foreign.status_code == 404
    assert foreign.json()["code"] == "appointment_not_found"
    stranger.conversation_id = client.conversation_id
    assert (await stranger.send({"kind": "text", "text": "чужое"})).status_code == 404

    cancelled = await http.post(
        f"{API}/appointments/{appointment['id']}/cancel", json={}, headers=client.headers
    )
    assert cancelled.status_code == 200, cancelled.text
    assert_matches_schema(cancelled.json(), "Appointment")
    assert cancelled.json()["cancelled_by"] == "client"
    await pump.drain()
    history = await client.history()
    assert history[1]["appointment"]["status"] == "cancelled"
    assert history[-1]["text"] == "Запись отменена, окно освободилось."


async def test_taken_slot_gets_alternatives_then_pick(
    http: httpx.AsyncClient, container: ApplicationContainer, master_id: UUID, pump: EventPump
) -> None:
    """Окно заняли → «уже заняли» и другие окна; выбор из предложения → заявка; повтор выбора — 409."""
    first = await new_client(http, container, 5011)
    second = await new_client(http, container, 5012)
    service = await service_id(http)
    slot = await free_slot(http, service)
    booking = {"kind": "book_slot", "service_id": service, "start": slot["start"]}
    assert (await first.send(booking)).status_code == 201
    await pump.drain()
    assert (await second.send(booking)).status_code == 201
    await pump.drain()

    offer = (await second.history())[-1]
    assert offer["kind"] == "slot_offer"
    assert offer["text"].startswith("Это время уже заняли. ")
    assert slot["start"] not in [s["start"] for s in offer["slots"]]
    picked = offer["slots"][0]
    pick = {"kind": "slot_pick", "offer_id": offer["id"], "start": picked["start"]}
    chosen = await second.send(pick)
    assert chosen.status_code == 201, chosen.text
    assert chosen.json()["text"] == picked["start"][11:16]
    assert (await second.send(pick)).json()["code"] == "offer_already_used"
    await pump.drain()

    history = await second.history()
    assert next(m for m in history if m["id"] == offer["id"])["selected_start"] == picked["start"]
    assert history[-1]["kind"] == "booking_card"
    assert history[-1]["appointment"]["start"] == picked["start"]


async def test_request_slots_and_decline(
    http: httpx.AsyncClient, container: ApplicationContainer, master_id: UUID, pump: EventPump
) -> None:
    """«Какое время свободно?» → окна на ближайший день; отклонение мастером → предупреждение."""
    client = await new_client(http, container, 5021)
    service = await service_id(http)
    asked = await client.send(
        {"kind": "request_slots", "text": "Какое время свободно?", "service_id": service}
    )
    assert asked.status_code == 201, asked.text
    await pump.drain()
    offer = (await client.history())[-1]
    assert offer["kind"] == "slot_offer"
    assert offer["text"].endswith("(60 мин) свободно:")
    assert len({s["start"][:10] for s in offer["slots"]}) == 1

    pick = {"kind": "slot_pick", "offer_id": offer["id"], "start": offer["slots"][-1]["start"]}
    assert (await client.send(pick)).status_code == 201
    await pump.drain()
    card = (await client.history())[-1]
    await container.mediator.send(DeclineAppointment(UUID(card["appointment"]["id"])))
    await pump.drain()
    history = await client.history()
    assert history[-1]["tone"] == "warning"
    assert history[-1]["text"].startswith("Алиса не сможет принять")
    assert next(m for m in history if m["id"] == card["id"])["appointment"]["cancelled_by"] == "master"


async def test_reschedule_keeps_old_until_confirmed(
    http: httpx.AsyncClient, container: ApplicationContainer, master_id: UUID, pump: EventPump
) -> None:
    """Перенос: новая заявка (новая карточка), старая запись освобождается после подтверждения."""
    client = await new_client(http, container, 5031)
    service = await service_id(http)
    slot = await free_slot(http, service)
    await client.send({"kind": "book_slot", "service_id": service, "start": slot["start"]})
    await pump.drain()
    old = (await client.history())[-1]["appointment"]
    await container.mediator.send(ConfirmAppointment(UUID(old["id"])))

    later = await free_slot(http, service, days_ahead=4)
    moved = await http.post(
        f"{API}/appointments/{old['id']}/reschedule", json={"start": later["start"]}, headers=client.headers
    )
    assert moved.status_code == 200, moved.text
    assert_matches_schema(moved.json(), "Appointment")
    assert moved.json()["status"] == "requested"
    await pump.drain()
    cards = [m for m in await client.history() if m["kind"] == "booking_card"]
    assert [c["appointment"]["status"] for c in cards] == ["confirmed", "requested"]

    await container.mediator.send(ConfirmAppointment(UUID(moved.json()["id"])))
    await pump.drain()
    cards = [m for m in await client.history() if m["kind"] == "booking_card"]
    assert [c["appointment"]["status"] for c in cards] == ["cancelled", "confirmed"]

    bad = await http.post(
        f"{API}/appointments/{old['id']}/reschedule",
        json={"start": "2026-10-20T10:00:00"},
        headers=client.headers,
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "validation_error"


async def test_feed_stream_replays_and_resets(
    http: httpx.AsyncClient, container: ApplicationContainer, master_id: UUID
) -> None:
    """Поток: досылка после Last-Event-ID, без него — только новое; устаревший id — reset."""
    client = await new_client(http, container, 5041)
    texts = ["Здравствуйте", "Есть парковка?", "Спасибо"]
    sent = await asyncio.gather(*(client.send({"kind": "text", "text": t}) for t in texts))
    assert all(r.status_code == 201 for r in sent)

    replay = await client.events("0")
    assert [f["id"] for f in replay] == ["1", "2", "3"]
    assert {f["event"] for f in replay} == {"message.created"}
    assert sorted(f["data"]["message"]["text"] for f in replay) == sorted(texts)
    for frame in replay:
        assert_matches_schema(frame["data"], "ConversationEvent")

    assert await client.events() == []
    assert [f["id"] for f in await client.events("2")] == ["3"]
    assert (await client.events("99"))[0]["event"] == "reset"

    async with container.engine.begin() as connection:
        await connection.execute(text("DELETE FROM conversations.feed_events WHERE seq = 1"))
    reset = await client.events("0")
    assert [(f["event"], f["id"], f["data"]) for f in reset] == [("reset", "3", {"type": "reset"})]

    stranger = Client(http, await login(http, container.mediator, 5042, "77015550422"))
    stranger.conversation_id = client.conversation_id
    denied = await http.get(f"{API}/conversations/{client.conversation_id}/events", headers=stranger.headers)
    assert denied.status_code == 404
    unauthenticated = await http.get(f"{API}/conversations/{client.conversation_id}/events")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["code"] == "invalid_session"


async def test_voice_upload_and_signed_media(
    http: httpx.AsyncClient, container: ApplicationContainer, master_id: UUID
) -> None:
    """Голосовое сохраняется в хранилище и отдаётся только по подписанной ссылке."""
    client = await new_client(http, container, 5051)
    audio = b"\x1aE\xdf\xa3" + b"opus" * 256
    response = await http.post(
        f"{API}/conversations/{client.conversation_id}/messages",
        files={"audio": ("voice.webm", audio, "audio/webm;codecs=opus")},
        data={"client_id": str(uuid4()), "duration": "3.4"},
        headers=client.headers,
    )
    assert response.status_code == 201, response.text
    voice = response.json()
    assert_matches_schema(voice, "Message")
    assert (voice["kind"], voice["duration"], voice["transcript"]) == ("voice", 3.4, None)

    media = await http.get(voice["audio_url"])
    assert media.status_code == 200
    assert media.content == audio
    assert media.headers["content-type"] == "audio/webm"
    tampered = await http.get(voice["audio_url"].replace("sig=", "sig=x"))
    assert tampered.status_code == 404

    too_long = await http.post(
        f"{API}/conversations/{client.conversation_id}/messages",
        files={"audio": ("voice.webm", audio, "audio/webm")},
        data={"client_id": str(uuid4()), "duration": "500"},
        headers=client.headers,
    )
    assert too_long.json()["code"] == "invalid_voice"


async def test_overlapping_appointments_are_rejected_by_database(
    container: ApplicationContainer, master_id: UUID
) -> None:
    """Исключающее ограничение: вторая открытая запись на пересекающееся время не сохранится."""
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    service = ServiceSnapshot(uuid4(), "Массаж", 60, None)

    def appointment(offset: timedelta) -> Appointment:
        return Appointment.request(
            appointment_id=container.id_generator.new(),
            master_id=master_id,
            client_id=uuid4(),
            service=service,
            client=ClientSnapshot.new_client("+77010000000", 1),
            slot=TimeSlot(start + offset, start + offset + timedelta(hours=1)),
            timezone="Asia/Almaty",
            confirm_within=timedelta(hours=2),
            change_deadline_hours=12,
            now=datetime.now(UTC),
        )

    async def save(offset: timedelta) -> None:
        uow = SqlAlchemyBookingUnitOfWork(
            container.session_factory, container.outbox_writer, container.id_generator
        )
        async with uow:
            uow.appointments.add(appointment(offset))
            await uow.commit()

    results = await asyncio.gather(save(timedelta(0)), save(timedelta(minutes=30)), return_exceptions=True)
    assert sorted(type(r).__name__ for r in results) == ["NoneType", "SlotTakenError"]
    assert any(isinstance(r, SlotTakenError) for r in results)
    await save(timedelta(hours=1))  # стык — не пересечение


async def test_unanswered_request_expires_by_scheduler(
    http: httpx.AsyncClient, container: ApplicationContainer, master_id: UUID, pump: EventPump
) -> None:
    """Задача планировщика отклоняет заявку без ответа; клиент видит предупреждение."""
    client = await new_client(http, container, 5061)
    service = await service_id(http)
    slot = await free_slot(http, service)
    await client.send({"kind": "book_slot", "service_id": service, "start": slot["start"]})
    await pump.drain()
    async with container.engine.begin() as connection:
        await connection.execute(
            text("UPDATE booking.appointments SET hold_until = now() - interval '1 minute'")
        )
        await connection.execute(
            text("UPDATE infra.scheduled_jobs SET due_at = now() - interval '1 minute' WHERE kind = :kind"),
            {"kind": "booking.expire_request"},
        )
    poller = ScheduledJobPoller(container.session_factory, container.job_handlers, container.clock)
    assert await poller.tick() == 1
    await pump.drain()
    history = await client.history()
    assert history[1]["appointment"]["cancelled_by"] == "system"
    assert history[-1]["text"].startswith("Заявка не подтверждена вовремя")
