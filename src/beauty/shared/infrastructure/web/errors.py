"""Отображение ошибок на HTTP-ответы в формате RFC 9457 (problem+json).

Все ошибки API — один формат::

    {"type": "about:blank", "title": "Not Found", "status": 404,
     "detail": "Мастер не найден", "code": "master_not_found"}

``code`` — расширение RFC 9457: машиночитаемый код, по которому клиент выбирает
реакцию (тексты ``detail`` могут меняться). Ошибки валидации запроса дополнительно
несут ``errors`` с JSON Pointer поля.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from beauty.shared.application.errors import ApplicationError
from beauty.shared.domain.errors import DomainError

PROBLEM_MEDIA_TYPE = "application/problem+json"

_DEFAULT_STATUSES: Mapping[str, int] = {
    "not_found": 404,
    "access_denied": 403,
    "conflict": 409,
    "concurrency_conflict": 409,
    "invariant_violation": 422,
    "domain_error": 422,
    "application_error": 400,
    "invalid_session": 401,
}


def problem_response(
    status: int,
    code: str,
    detail: str,
    *,
    errors: Sequence[Mapping[str, str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Ответ RFC 9457 с расширением ``code``."""
    content: dict[str, Any] = {
        "type": "about:blank",
        "title": _title(status),
        "status": status,
        "detail": detail,
        "code": code,
    }
    if errors:
        content["errors"] = list(errors)
    return JSONResponse(status_code=status, content=content, media_type=PROBLEM_MEDIA_TYPE, headers=headers)


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


class HttpErrorMapper:
    """Реестр «код ошибки → HTTP-статус» и обработчики исключений приложения.

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
        app.add_exception_handler(DomainError, self._handle_domain)  # type: ignore[arg-type]
        app.add_exception_handler(ApplicationError, self._handle_domain)  # type: ignore[arg-type]
        app.add_exception_handler(RequestValidationError, self._handle_validation)  # type: ignore[arg-type]
        app.add_exception_handler(StarletteHTTPException, self._handle_http)  # type: ignore[arg-type]

    async def _handle_domain(self, _request: Request, error: DomainError | ApplicationError) -> JSONResponse:
        """Доменная или прикладная ошибка → статус по коду."""
        fallback = 422 if isinstance(error, DomainError) else 400
        return problem_response(self.status_for(error.code, fallback), error.code, str(error))

    @staticmethod
    async def _handle_validation(_request: Request, error: RequestValidationError) -> JSONResponse:
        """Невалидный запрос (параметры, тело) → 422 с указанием полей."""
        fields = [
            {
                "pointer": "/" + "/".join(str(part) for part in item.get("loc", ())),
                "detail": str(item.get("msg", "")),
            }
            for item in error.errors()
        ]
        return problem_response(422, "validation_error", "Некорректный запрос", errors=fields)

    @staticmethod
    async def _handle_http(_request: Request, error: StarletteHTTPException) -> JSONResponse:
        """HTTP-исключения фреймворка (404 маршрута, 405 метода) — тоже problem+json."""
        detail = error.detail if isinstance(error.detail, str) else _title(error.status_code)
        return problem_response(error.status_code, f"http_{error.status_code}", detail, headers=error.headers)
