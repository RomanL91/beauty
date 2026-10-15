"""Веб-утилиты для FastAPI: перевод ошибок в HTTP-ответы и Server-Sent Events."""

from beauty.shared.infrastructure.web.errors import HttpErrorMapper
from beauty.shared.infrastructure.web.sse import ServerSentEvent

__all__ = ["HttpErrorMapper", "ServerSentEvent"]
