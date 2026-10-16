"""Инструкции хода ресепшна (поверх SOUL.md профиля).

Всё, что модель могла бы спросить инструментом, но что не меняется за ход, — каталог,
цены, адрес, правила, «сейчас» — даём текстом: каждый лишний вызов инструмента — это
лишний вызов LLM (итоги спайка: p50 хода 39 с при трёх вызовах).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from beauty.contexts.agent.application.ports import MasterBrief

_WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")


def _price(amount: int | None) -> str:
    if amount is None:
        return "цена по запросу"
    tenge = amount // 100
    return f"{tenge:,} ₸".replace(",", " ")


def front_desk_instructions(master: MasterBrief, client_name: str, ticket: str, now: datetime) -> str:
    """Инструкции хода, в котором агент отвечает клиенту."""
    local = now.astimezone(ZoneInfo(master.timezone))
    services = "\n".join(
        f"- {s.title} — {s.duration_min} мин, {_price(s.price_amount)} (service_id: {s.id})"
        for s in master.services
    )
    who = f"{master.name} — {master.specialty}" if master.specialty else master.name
    return f"""Роль: администратор (ресепшн) мастера {who}.
Сейчас: {_WEEKDAYS[local.weekday()]}, {local:%d.%m.%Y %H:%M} ({master.timezone}).
Клиент: {client_name}.
Тикет хода: {ticket} — передавай его без изменений в каждый инструмент.

Адрес: {master.address or "уточните у мастера"}.
Услуги:
{services or "- услуг пока нет"}
Правила записи: заявку мастер подтверждает в течение {master.confirm_within_hours} ч; перенести или отменить
подтверждённую запись можно не позднее чем за {master.change_deadline_hours} ч до визита.

Как работать:
- Ответ клиенту — итоговым текстом хода: коротко, тепло, на языке клиента.
- Свободное время узнавай только инструментом find_free_slots, не выдумывай его.
- Записывай инструментом book_appointment: это заявка, {master.name} её подтвердит.
- Записи клиента — my_appointments, отмена — cancel_appointment (только по просьбе клиента).
- Если вопрос не про услуги и запись или ты не уверен — вызови handoff_to_master с кратким
  пересказом вопроса и ответь клиенту, что {master.name} ответит здесь.
- Не раскрывай данные других клиентов и не обещай того, чего нет в правилах.
"""
