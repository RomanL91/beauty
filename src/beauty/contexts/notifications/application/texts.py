"""Что и кому сообщить по событию соседнего контекста — чистые функции.

Время в событиях Booking уже в поясе мастера (снимок записи), поэтому «завтра в 12:00»
считается от «сегодня» в том же поясе.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from beauty.contexts.notifications.application.ports import PushPayload
from beauty.contexts.notifications.domain.subscription import PushApp
from beauty.shared.application.phrases import capitalize, day_phrase, time_label

MAX_BODY = 140

TO_CLIENT_MESSAGE_KINDS = frozenset({"text", "slot_offer", "announcement"})
FROM_CLIENT_MESSAGE_KINDS = frozenset({"text", "voice"})


@dataclass(frozen=True, slots=True)
class Audience:
    """Кому: приложение мастера или клиентское (конкретной учётной записи)."""

    app: PushApp
    master_id: UUID
    account_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Notification:
    """Уведомление адресату."""

    audience: Audience
    payload: PushPayload


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_BODY else text[: MAX_BODY - 1] + "…"


def _when(appointment: Mapping[str, Any], today: date) -> tuple[str, str]:
    """(«завтра в 12:00», дата YYYY-MM-DD) по снимку записи."""
    start = datetime.fromisoformat(str(appointment["start"]))
    return f"{day_phrase(start.date(), today)} в {time_label(start)}", start.date().isoformat()


def _service(appointment: Mapping[str, Any]) -> str:
    service = appointment.get("service")
    return str(service.get("title")) if isinstance(service, Mapping) and service.get("title") else "визит"


def _client(appointment: Mapping[str, Any]) -> str:
    client = appointment.get("client")
    return str(client.get("display_name")) if isinstance(client, Mapping) else "Клиент"


def appointment_notifications(
    event: str, payload: Mapping[str, Any], master_name: str, today: date
) -> list[Notification]:
    """События записи (``event`` — последнее слово ключа: requested, confirmed, cancelled…)."""
    appointment = payload["appointment"]
    master_id = UUID(str(payload["master_id"]))
    client_id = UUID(str(payload["client_id"]))
    when, day = _when(appointment, today)
    service = _service(appointment)
    tag = f"appointment-{payload['appointment_id']}"
    to_master = Audience(PushApp.MASTER, master_id)
    to_client = Audience(PushApp.CLIENT, master_id, client_id)
    schedule = f"/schedule/{day}"
    if event == "requested":
        title = "Перенос записи" if payload.get("reschedule_of") else "Новая заявка"
        body = f"{_client(appointment)} · {service} · {when}"
        return [Notification(to_master, PushPayload("appointment_requested", title, body, schedule, tag))]
    if event == "confirmed":
        body = f"Запись подтверждена: {when} — {service}"
        return [
            Notification(to_client, PushPayload("appointment_confirmed", master_name, body, "/chat", tag))
        ]
    if event == "reminder_due":
        body = f"Напоминаем: {when} — {service}. Ждём вас!"
        return [Notification(to_client, PushPayload("reminder", master_name, body, "/chat", tag))]
    if event == "cancelled":
        return _cancelled(payload, master_name, when, service, schedule, tag)
    return []


def _cancelled(
    payload: Mapping[str, Any], master_name: str, when: str, service: str, schedule: str, tag: str
) -> list[Notification]:
    appointment = payload["appointment"]
    master_id = UUID(str(payload["master_id"]))
    reason = payload.get("reason")
    if reason == "client_cancelled":
        body = f"{_client(appointment)} · {service} · {when}"
        audience = Audience(PushApp.MASTER, master_id)
        return [
            Notification(
                audience, PushPayload("appointment_declined", "Клиент отменил запись", body, schedule, tag)
            )
        ]
    bodies = {
        "declined": "Не сможет принять в это время — выберите другое окно в чате",
        "expired": "Заявка не подтверждена вовремя — выберите другое время в чате",
        "master_cancelled": f"Запись {when} отменена — выберите другое время в чате",
    }
    text = bodies.get(str(reason))
    if text is None:  # перенос заменил запись — сообщать нечего
        return []
    audience = Audience(PushApp.CLIENT, master_id, UUID(str(payload["client_id"])))
    return [Notification(audience, PushPayload("appointment_declined", master_name, text, "/chat", tag))]


def message_notifications(
    payload: Mapping[str, Any], master_name: str, client_name: str | None
) -> list[Notification]:
    """Новое сообщение в переписке (``conversations.message.added``)."""
    master_id = UUID(str(payload["master_id"]))
    conversation_id = str(payload["conversation_id"])
    author, kind = payload["author"], payload["kind"]
    preview = _short(str(payload.get("preview") or ""))
    dialog = f"/chats/{conversation_id}"
    tag = f"chat-{conversation_id}"
    if author in ("agent", "master") and kind in TO_CLIENT_MESSAGE_KINDS:
        audience = Audience(PushApp.CLIENT, master_id, UUID(str(payload["client_id"])))
        return [Notification(audience, PushPayload("message", master_name, preview, "/chat", tag))]
    if author == "agent" and kind == "agent_note":
        audience = Audience(PushApp.MASTER, master_id)
        return [Notification(audience, PushPayload("message", "Нужен ваш ответ", preview, dialog, tag))]
    if author == "client" and payload.get("handler") == "master" and kind in FROM_CLIENT_MESSAGE_KINDS:
        audience = Audience(PushApp.MASTER, master_id)
        title = capitalize(client_name or "клиент")
        return [Notification(audience, PushPayload("message", title, preview, dialog, tag))]
    return []


def office_notifications(payload: Mapping[str, Any]) -> list[Notification]:
    """Ответ агента в ленте поручений (``agent.office.feed_changed``)."""
    message = payload.get("message") or {}
    if payload.get("change") != "message.created" or message.get("author") != "agent":
        return []
    text = _short(str(message.get("text") or ""))
    if message.get("kind") == "broadcast":
        text = "Черновик рассылки готов — проверьте и отправьте"
    if not text:
        return []
    audience = Audience(PushApp.MASTER, UUID(str(payload["master_id"])))
    return [Notification(audience, PushPayload("task_done", "Поручение", text, "/assistant", "assistant"))]
