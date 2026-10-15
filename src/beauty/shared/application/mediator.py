"""Медиатор: единая точка входа для команд и запросов.

Слой представления (HTTP, бот, консьюмер брокера, MCP-инструмент агента) знает только
о сообщениях и медиаторе, но не о конкретных обработчиках (DIP). Сквозная
функциональность — логирование, повтор при конфликте конкурентности — подключается
цепочкой middleware (Chain of Responsibility) и не дублируется в обработчиках.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, cast

from beauty.shared.application.cqrs import Handler, Request

type NextStep = Callable[[Request[Any]], Awaitable[Any]]
"""Следующее звено конвейера."""

type HandlerFactory = Callable[[], Handler[Any, Any]]
"""Фабрика обработчика: вызывается на каждое сообщение (и на каждую попытку)."""


class Middleware(ABC):
    """Звено конвейера обработки сообщений."""

    @abstractmethod
    async def __call__(self, message: Request[Any], next_step: NextStep) -> Any:
        """Выполнить свою часть работы и передать управление дальше."""


class HandlerNotRegisteredError(LookupError):
    """Для типа сообщения не зарегистрирован обработчик."""


class Mediator:
    """Реестр обработчиков и исполнитель конвейера middleware."""

    def __init__(self, middlewares: Sequence[Middleware] = ()) -> None:
        """Создать медиатор с упорядоченным списком middleware (внешний — первый)."""
        self._factories: dict[type[Request[Any]], HandlerFactory] = {}
        self._middlewares = tuple(middlewares)

    def register[M: Request[Any]](
        self, message_type: type[M], factory: Callable[[], Handler[M, Any]]
    ) -> None:
        """Зарегистрировать фабрику обработчика для типа сообщения."""
        if message_type in self._factories:
            raise ValueError(f"Обработчик для {message_type.__name__} уже зарегистрирован")
        self._factories[message_type] = cast(HandlerFactory, factory)

    async def send[R](self, message: Request[R]) -> R:
        """Провести сообщение через конвейер и вернуть результат обработчика."""
        factory = self._resolve(type(message))
        pipeline = self._build_pipeline(factory)
        return cast(R, await pipeline(message))

    def _resolve(self, message_type: type[Request[Any]]) -> HandlerFactory:
        """Найти фабрику обработчика."""
        try:
            return self._factories[message_type]
        except KeyError as error:
            raise HandlerNotRegisteredError(message_type.__name__) from error

    def _build_pipeline(self, factory: HandlerFactory) -> NextStep:
        """Свернуть middleware вокруг вызова обработчика."""

        async def invoke_handler(message: Request[Any]) -> Any:
            return await factory().handle(message)

        pipeline: NextStep = invoke_handler
        for middleware in reversed(self._middlewares):
            pipeline = _Link(middleware, pipeline)
        return pipeline


class _Link:
    """Связка «middleware → следующее звено» (замыкание в виде объекта)."""

    __slots__ = ("_middleware", "_next")

    def __init__(self, middleware: Middleware, next_step: NextStep) -> None:
        """Запомнить звено и его продолжение."""
        self._middleware = middleware
        self._next = next_step

    async def __call__(self, message: Request[Any]) -> Any:
        """Выполнить middleware с продолжением."""
        return await self._middleware(message, self._next)
