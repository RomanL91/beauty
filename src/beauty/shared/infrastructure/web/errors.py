"""Отображение доменных и прикладных ошибок на HTTP-ответы."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from beauty.shared.application.errors import ApplicationError
from beauty.shared.domain.errors import DomainError

_DEFAULT_STATUSES: Mapping[str, int] = {
    "not_found": 404,
    "access_denied": 403,
    "conflict": 409,
    "concurrency_conflict": 409,
    "invariant_violation": 422,
    "domain_error": 422,
    "application_error": 400,
}


class HttpErrorMapper:
    """Реестр «код ошибки → HTTP-статус».

    Контексты дополняют реестр своими кодами при регистрации модуля, поэтому
    обработчик исключений один на всё приложение и не знает о классах контекстов.
    """

    def __init__(self) -> None:
        """Заполнить статусы по умолчанию."""
        self._statuses: dict[str, int] = dict(_DEFAULT_STATUSES)

    def register(self, code: str, status: int) -> None:
        """Назначить статус коду ошибки."""
        self._statuses[code] = status

    def status_for(self, code: str, fallback: int) -> int:
        """Статус для кода (или запасной)."""
        return self._statuses.get(code, fallback)

    def install(self, app: FastAPI) -> None:
        """Подключить обработчики исключений к приложению."""
        app.add_exception_handler(DomainError, self._handle)  # type: ignore[arg-type]
        app.add_exception_handler(ApplicationError, self._handle)  # type: ignore[arg-type]

    async def _handle(self, _request: Request, error: DomainError | ApplicationError) -> JSONResponse:
        """Сформировать JSON-ответ об ошибке."""
        fallback = 422 if isinstance(error, DomainError) else 400
        return JSONResponse(
            status_code=self.status_for(error.code, fallback),
            content={"error": {"code": error.code, "message": str(error)}},
        )
