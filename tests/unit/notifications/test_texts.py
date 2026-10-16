"""Кому и что сообщить по событиям записей, переписки и поручений."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from beauty.contexts.notifications.application.texts import (
    Audience,
    appointment_notifications,
    message_notifications,
    office_notifications,
)
from beauty.contexts.notifications.domain.subscription import PushApp

MASTER = UUID(int=1)
CLIENT = UUID(int=2)
TODAY = date(2026, 10, 16)  # пятница
TO_MASTER = Audience(PushApp.MASTER, MASTER)
TO_CLIENT = Audience(PushApp.CLIENT, MASTER, CLIENT)


def booking_event(**extra: Any) -> dict[str, Any]:
    """Событие записи на завтра 12:00."""
    return {
        "appointment_id": str(UUID(int=7)),
        "master_id": str(MASTER),
        "client_id": str(CLIENT),
        "appointment": {
            "start": "2026-10-17T12:00:00+05:00",
            "service": {"title": "Массаж спины"},
            "client": {"display_name": "Дарья К."},
        },
        **extra,
    }


def test_appointment_events() -> None:
    """Заявка — мастеру; подтверждение и напоминание — клиенту; ссылки и теги."""
    (requested,) = appointment_notifications("requested", booking_event(), "Алиса", TODAY)
    assert requested.audience == TO_MASTER
    assert requested.payload.kind == "appointment_requested"
    assert requested.payload.body == "Дарья К. · Массаж спины · завтра в 12:00"
    assert (requested.payload.url, requested.payload.tag) == (
        "/schedule/2026-10-17",
        f"appointment-{UUID(int=7)}",
    )
    (moved,) = appointment_notifications("requested", booking_event(reschedule_of="x"), "Алиса", TODAY)
    assert moved.payload.title == "Перенос записи"

    (confirmed,) = appointment_notifications("confirmed", booking_event(), "Алиса", TODAY)
    assert (confirmed.audience, confirmed.payload.title, confirmed.payload.url) == (
        TO_CLIENT,
        "Алиса",
        "/chat",
    )
    assert confirmed.payload.body == "Запись подтверждена: завтра в 12:00 — Массаж спины"
    (reminder,) = appointment_notifications("reminder_due", booking_event(), "Алиса", TODAY)
    assert (reminder.payload.kind, reminder.payload.body) == (
        "reminder",
        "Напоминаем: завтра в 12:00 — Массаж спины. Ждём вас!",
    )
    assert appointment_notifications("completed", booking_event(), "Алиса", TODAY) == []


def test_cancellations_go_to_the_other_side() -> None:
    """Отменил клиент — мастеру; отклонил, истекла, отменил мастер — клиенту; перенос — никому."""
    (by_client,) = appointment_notifications(
        "cancelled", booking_event(reason="client_cancelled"), "Алиса", TODAY
    )
    assert (by_client.audience, by_client.payload.title) == (TO_MASTER, "Клиент отменил запись")
    for reason in ("declined", "expired", "master_cancelled"):
        (note,) = appointment_notifications("cancelled", booking_event(reason=reason), "Алиса", TODAY)
        assert (note.audience, note.payload.kind) == (TO_CLIENT, "appointment_declined")
    assert appointment_notifications("cancelled", booking_event(reason="rescheduled"), "Алиса", TODAY) == []


def message_event(author: str, kind: str, handler: str = "agent") -> dict[str, Any]:
    """Новое сообщение в переписке."""
    return {
        "conversation_id": str(UUID(int=9)),
        "master_id": str(MASTER),
        "client_id": str(CLIENT),
        "author": author,
        "kind": kind,
        "preview": "Есть   ли парковка?",
        "handler": handler,
    }


def test_messages_wake_only_who_needs_it() -> None:
    """Ответ клиенту — клиенту; вопрос агента — мастеру; клиент пишет мастеру — мастеру."""
    (reply,) = message_notifications(message_event("agent", "text"), "Алиса", None)
    assert (reply.audience, reply.payload.url, reply.payload.body) == (
        TO_CLIENT,
        "/chat",
        "Есть ли парковка?",
    )
    (note,) = message_notifications(message_event("agent", "agent_note"), "Алиса", None)
    assert (note.audience, note.payload.title, note.payload.url) == (
        TO_MASTER,
        "Нужен ваш ответ",
        f"/chats/{UUID(int=9)}",
    )
    (direct,) = message_notifications(message_event("client", "text", handler="master"), "Алиса", "дарья К.")
    assert (direct.audience, direct.payload.title) == (TO_MASTER, "Дарья К.")
    assert message_notifications(message_event("client", "text"), "Алиса", None) == []  # ведёт агент
    assert message_notifications(message_event("agent", "booking_card"), "Алиса", None) == []
    assert message_notifications(message_event("agent", "system"), "Алиса", None) == []


def test_office_reply_wakes_the_master() -> None:
    """Ответ агента на поручение — мастеру; поручения самого мастера и обновления — нет."""
    created = {
        "master_id": str(MASTER),
        "change": "message.created",
        "message": {"author": "agent", "kind": "text", "text": "Воскресенье закрыто."},
    }
    (done,) = office_notifications(created)
    assert (done.audience, done.payload.kind, done.payload.url) == (TO_MASTER, "task_done", "/assistant")
    assert office_notifications({**created, "change": "message.updated"}) == []
    assert office_notifications({**created, "message": {"author": "master", "text": "Закрой"}}) == []
