"""Сценарная OpenAI-совместимая «модель» для локального прогона ИИ-администратора без ключа LLM.

Hermes ходит сюда как к провайдеру ``custom`` (``POST /v1/chat/completions``), а «модель»
ведёт ход по простому сценарию, вызывая наши MCP-инструменты настоящими tool calls:

* «запиши / массаж / окно» → ``find_free_slots`` → ``book_appointment`` (первое окно) → ответ;
* «мои записи» → ``my_appointments`` → ответ;
* вопрос не про запись («парковка», «?») → ``handoff_to_master`` → ответ;
* иначе — приветствие.

Тикет хода и ``service_id`` берутся из инструкций запуска, как это делала бы модель.
Запуск: ``python devtools/fake_llm.py`` (порт ``FAKE_LLM_PORT``, по умолчанию 8090).
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections.abc import Iterator
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

TICKET = re.compile(r"Тикет хода: (t-[a-z0-9]+)")
SERVICE = re.compile(r"^- (?P<title>.+?) — .*\(service_id: (?P<id>[0-9a-f-]{36})\)", re.MULTILINE)
# Hermes оборачивает результат инструмента и кладёт JSON строкой — кавычки экранированы.
START = re.compile(r'\\?"start\\?"\s*:\s*\\?"([^"\\]+)')
BOOKING_WORDS = ("запиш", "записа", "окн", "свобод", "массаж", "маникюр", "стриж")

app = FastAPI(title="fake-llm")


def _text(content: Any) -> str:
    """Содержимое сообщения OpenAI — строка или список частей."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


class Turn:
    """Ход глазами «модели»: инструкции, реплика клиента, уже сделанные вызовы."""

    def __init__(self, body: dict[str, Any]) -> None:
        """Разобрать запрос chat completions."""
        messages: list[dict[str, Any]] = body.get("messages") or []
        self.system = "\n".join(_text(m.get("content")) for m in messages if m.get("role") == "system")
        last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
        self.user = _text(messages[last_user].get("content")) if last_user >= 0 else ""
        self.tools = [t["function"]["name"] for t in body.get("tools") or [] if "function" in t]
        names: dict[str, str] = {}
        self.results: dict[str, str] = {}
        for message in messages[last_user + 1 :]:
            for call in message.get("tool_calls") or []:
                names[call["id"]] = call["function"]["name"]
            if message.get("role") == "tool":
                name = names.get(message.get("tool_call_id", ""), "")
                self.results[self._logical(name)] = _text(message.get("content"))

    @staticmethod
    def _logical(name: str) -> str:
        for logical in (
            "find_free_slots",
            "book_appointment",
            "my_appointments",
            "cancel_appointment",
            "handoff_to_master",
        ):
            if name.endswith(logical):
                return logical
        return name

    def tool(self, logical: str) -> str | None:
        """Как инструмент называется у Hermes (с префиксом MCP-сервера)."""
        return next((name for name in self.tools if name.endswith(logical)), None)

    def service_id(self) -> str | None:
        """Услуга из каталога: по словам клиента, иначе первая."""
        services = list(SERVICE.finditer(self.system))
        wanted = self.user.lower()
        for match in services:
            if match.group("title").split()[0].lower()[:5] in wanted:
                return match.group("id")
        return services[0].group("id") if services else None


type Step = tuple[str | None, dict[str, Any] | None, str]


def answer(text: str) -> Step:
    """Итоговый текст хода."""
    return None, None, text


def call(tool: str, arguments: dict[str, Any]) -> Step:
    """Вызов инструмента."""
    return tool, arguments, ""


def once(turn: Turn, tool: str, arguments: dict[str, Any], reply: str) -> Step:
    """Один вызов инструмента, затем ответ."""
    return answer(reply) if tool in turn.results else call(tool, arguments)


def booking(turn: Turn, ticket: str) -> Step:
    """Окна → заявка на первое окно → ответ."""
    service = turn.service_id()
    if "find_free_slots" not in turn.results:
        return call("find_free_slots", {"ticket": ticket, "service_id": service})
    if "book_appointment" not in turn.results:
        slot = START.search(turn.results["find_free_slots"])
        if slot is None:
            return answer("Свободных окон пока нет — мастер подскажет, когда появятся.")
        return call("book_appointment", {"ticket": ticket, "service_id": service, "start": slot.group(1)})
    booked = START.search(turn.results["book_appointment"])
    when = booked.group(1)[:16].replace("T", " в ") if booked else "ближайшее окно"
    return answer(f"Записала вас на {when}. Мастер подтвердит заявку — карточка уже в чате.")


def decide(turn: Turn) -> Step:
    """Следующий шаг хода по реплике клиента."""
    found = TICKET.search(turn.system)
    if found is None or not turn.tools:
        return answer("Готово.")  # служебные вызовы Hermes (заголовок сессии и т. п.)
    ticket = found.group(1)
    text = turn.user.lower()
    if any(word in text for word in BOOKING_WORDS):
        return booking(turn, ticket)
    if "мои записи" in text or "когда я" in text:
        return once(turn, "my_appointments", {"ticket": ticket}, "Вот ваши записи. Что-нибудь изменить?")
    if "?" in text or "парков" in text:
        summary = {"ticket": ticket, "summary": turn.user.strip()}
        return once(turn, "handoff_to_master", summary, "Уточню у мастера — ответ придёт сюда же.")
    return answer("Здравствуйте! Я администратор мастера. Подсказать по услугам или записать вас?")


def completion(body: dict[str, Any]) -> dict[str, Any]:
    """Ответ chat completions (без стриминга)."""
    turn = Turn(body)
    logical, arguments, text = decide(turn)
    name = turn.tool(logical) if logical else None
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    finish = "stop"
    if name is not None:
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                }
            ],
        }
        finish = "tool_calls"
    print(f"[fake-llm] {turn.user[:40]!r} → {name or repr((text or '')[:60])}", flush=True)
    for tool, result in turn.results.items():
        print(f"[fake-llm]   {tool}: {' '.join(result.split())[-160:]}", flush=True)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "fake"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def chunks(result: dict[str, Any]) -> Iterator[str]:
    """Тот же ответ в виде SSE-потока (если клиент попросил ``stream``)."""
    choice = result["choices"][0]
    delta = dict(choice["message"])
    for index, call in enumerate(delta.get("tool_calls") or []):
        call["index"] = index
    base = {key: result[key] for key in ("id", "created", "model")} | {"object": "chat.completion.chunk"}
    yield f"data: {json.dumps(base | {'choices': [{'index': 0, 'delta': delta}]}, ensure_ascii=False)}\n\n"
    final = {"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}
    yield f"data: {json.dumps(base | {'choices': [final], 'usage': result['usage']})}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat(request: Request) -> Any:
    """OpenAI chat completions."""
    body = await request.json()
    result = completion(body)
    if body.get("stream"):
        return StreamingResponse(chunks(result), media_type="text/event-stream")
    return JSONResponse(result)


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    """Список моделей."""
    return {"object": "list", "data": [{"id": "fake-front-desk", "object": "model", "owned_by": "beauty"}]}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("FAKE_LLM_PORT", "8090")))
