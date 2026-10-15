"""Тесты медиатора и middleware."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from beauty.shared.application.cqrs import Command, Handler, Query, Request
from beauty.shared.application.errors import ConcurrencyConflictError
from beauty.shared.application.mediator import HandlerNotRegisteredError, Mediator, Middleware, NextStep
from beauty.shared.application.middleware import ConcurrencyRetryMiddleware


@dataclass(frozen=True, slots=True)
class Add(Command[int]):
    a: int
    b: int


@dataclass(frozen=True, slots=True)
class Echo(Query[str]):
    text: str


class AddHandler(Handler[Add, int]):
    async def handle(self, message: Add) -> int:
        return message.a + message.b


class FlakyAdd(Handler[Add, int]):
    """Падает конфликтом первые ``failures`` раз (счётчик общий для всех экземпляров)."""

    calls = 0

    def __init__(self, failures: int) -> None:
        self._failures = failures

    async def handle(self, message: Add) -> int:
        FlakyAdd.calls += 1
        if FlakyAdd.calls <= self._failures:
            raise ConcurrencyConflictError()
        return message.a + message.b


class Recorder(Middleware):
    def __init__(self, name: str, journal: list[str]) -> None:
        self._name, self._journal = name, journal

    async def __call__(self, message: Request[Any], next_step: NextStep) -> Any:
        self._journal.append(f"{self._name}:before")
        result = await next_step(message)
        self._journal.append(f"{self._name}:after")
        return result


async def test_dispatches_to_registered_handler() -> None:
    """Сообщение доходит до своего обработчика."""
    mediator = Mediator()
    mediator.register(Add, AddHandler)
    assert await mediator.send(Add(2, 3)) == 5


async def test_unregistered_message_fails_loudly() -> None:
    """Незарегистрированный тип — явная ошибка."""
    with pytest.raises(HandlerNotRegisteredError):
        await Mediator().send(Add(1, 1))


async def test_duplicate_registration_rejected() -> None:
    """Один тип — один обработчик."""
    mediator = Mediator()
    mediator.register(Add, AddHandler)
    with pytest.raises(ValueError, match="уже зарегистрирован"):
        mediator.register(Add, AddHandler)


async def test_middlewares_wrap_in_declared_order() -> None:
    """Первый middleware — внешний."""
    journal: list[str] = []
    mediator = Mediator(middlewares=(Recorder("outer", journal), Recorder("inner", journal)))
    mediator.register(Add, AddHandler)
    await mediator.send(Add(1, 1))
    assert journal == ["outer:before", "inner:before", "inner:after", "outer:after"]


async def test_retry_middleware_recovers_from_conflict() -> None:
    """Конфликт конкурентности повторяется с новым обработчиком."""
    FlakyAdd.calls = 0
    mediator = Mediator(middlewares=(ConcurrencyRetryMiddleware(attempts=3, base_delay=0),))
    mediator.register(Add, lambda: FlakyAdd(failures=2))
    assert await mediator.send(Add(1, 2)) == 3
    assert FlakyAdd.calls == 3


async def test_retry_middleware_gives_up() -> None:
    """После исчерпания попыток конфликт пробрасывается."""
    FlakyAdd.calls = 0
    mediator = Mediator(middlewares=(ConcurrencyRetryMiddleware(attempts=2, base_delay=0),))
    mediator.register(Add, lambda: FlakyAdd(failures=5))
    with pytest.raises(ConcurrencyConflictError):
        await mediator.send(Add(1, 2))
    assert FlakyAdd.calls == 2


async def test_queries_are_not_retried() -> None:
    """Запросы проходят мимо повтора."""

    class FailingEcho(Handler[Echo, str]):
        calls = 0

        async def handle(self, message: Echo) -> str:
            FailingEcho.calls += 1
            raise ConcurrencyConflictError()

    mediator = Mediator(middlewares=(ConcurrencyRetryMiddleware(attempts=3, base_delay=0),))
    mediator.register(Echo, FailingEcho)
    with pytest.raises(ConcurrencyConflictError):
        await mediator.send(Echo("x"))
    assert FailingEcho.calls == 1
