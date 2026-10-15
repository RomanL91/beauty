"""Контроллер HTTP API Identity."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse

from beauty.contexts.identity.application.commands import (
    ExchangeChallengeForSession,
    RefreshSession,
    RevokeSession,
    StartTelegramAuth,
)
from beauty.contexts.identity.application.dto import SessionTokens
from beauty.contexts.identity.application.errors import InvalidSessionError, SessionReuseError
from beauty.contexts.identity.application.queries import GetChallengeStatus
from beauty.contexts.identity.presentation.api.cookies import (
    CHALLENGE_COOKIE,
    REFRESH_COOKIE,
    AuthCookiePolicy,
)
from beauty.contexts.identity.presentation.api.schemas import (
    ChallengeStatusResponse,
    SessionResponse,
    StartChallengeResponse,
)
from beauty.contexts.identity.presentation.api.stream import ChallengeStatusStream
from beauty.shared.application.mediator import Mediator
from beauty.shared.domain.clock import Clock
from beauty.shared.infrastructure.realtime.hub import RealtimeHub

ChallengeSecret = Annotated[str | None, Cookie(alias=CHALLENGE_COOKIE)]
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


class IdentityApiController:
    """Эндпоинты входа через Telegram и управления сессией.

    Контроллер тонкий: переводит HTTP в команды/запросы медиатора и результаты —
    в ответы и cookie. Ошибки домена и приложения превращает в HTTP общий
    ``HttpErrorMapper``.
    """

    def __init__(
        self,
        mediator: Mediator,
        hub: RealtimeHub,
        cookies: AuthCookiePolicy,
        clock: Clock,
        stream_poll_interval: float = 5.0,
        stream_max_duration: float = 330.0,
    ) -> None:
        """Получить зависимости."""
        self._mediator = mediator
        self._hub = hub
        self._cookies = cookies
        self._clock = clock
        self._stream_poll_interval = stream_poll_interval
        self._stream_max_duration = stream_max_duration

    def router(self) -> APIRouter:
        """Собрать роутер с привязанными методами."""
        router = APIRouter(prefix="/auth", tags=["auth"])
        router.add_api_route(
            "/telegram/challenges",
            self.start_challenge,
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            response_model=StartChallengeResponse,
            summary="Начать вход через Telegram",
        )
        router.add_api_route(
            "/telegram/challenges/{challenge_id}",
            self.challenge_status,
            methods=["GET"],
            response_model=ChallengeStatusResponse,
            summary="Статус входа",
        )
        router.add_api_route(
            "/telegram/challenges/{challenge_id}/events",
            self.challenge_events,
            methods=["GET"],
            response_class=StreamingResponse,
            summary="SSE-поток статуса входа",
        )
        router.add_api_route(
            "/telegram/challenges/{challenge_id}/session",
            self.exchange_for_session,
            methods=["POST"],
            response_model=SessionResponse,
            summary="Обменять завершённый вход на сессию",
        )
        router.add_api_route(
            "/session/refresh",
            self.refresh_session,
            methods=["POST"],
            response_model=SessionResponse,
            summary="Обновить access-токен",
        )
        router.add_api_route(
            "/session/logout",
            self.logout,
            methods=["POST"],
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Выйти",
        )
        return router

    async def start_challenge(self, response: Response) -> StartChallengeResponse:
        """Создать вход и положить секрет браузера в httpOnly-cookie."""
        started = await self._mediator.send(StartTelegramAuth())
        self._cookies.set_challenge(response, started.browser_secret)
        return StartChallengeResponse(
            challenge_id=started.challenge_id,
            deep_link=started.deep_link,
            confirmation_code=started.confirmation_code,
            expires_at=started.expires_at,
        )

    async def challenge_status(
        self, challenge_id: UUID, secret: ChallengeSecret = None
    ) -> ChallengeStatusResponse:
        """Текущий статус входа (только для начавшего браузера)."""
        view = await self._mediator.send(GetChallengeStatus(challenge_id, secret or ""))
        return ChallengeStatusResponse(
            challenge_id=view.challenge_id, status=view.status, expires_at=view.expires_at
        )

    async def challenge_events(
        self, request: Request, challenge_id: UUID, secret: ChallengeSecret = None
    ) -> StreamingResponse:
        """SSE: статус входа до финального состояния."""
        await self._mediator.send(GetChallengeStatus(challenge_id, secret or ""))
        stream = ChallengeStatusStream(
            mediator=self._mediator,
            hub=self._hub,
            challenge_id=challenge_id,
            browser_secret=secret or "",
            is_disconnected=request.is_disconnected,
            poll_interval=self._stream_poll_interval,
            max_duration=self._stream_max_duration,
        )
        return StreamingResponse(
            stream.events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    async def exchange_for_session(
        self, challenge_id: UUID, response: Response, secret: ChallengeSecret = None
    ) -> SessionResponse:
        """Погасить вход и открыть сессию."""
        tokens = await self._mediator.send(ExchangeChallengeForSession(challenge_id, secret or ""))
        self._cookies.clear_challenge(response)
        return self._session_response(response, tokens)

    async def refresh_session(
        self, response: Response, refresh: RefreshCookie = None
    ) -> SessionResponse | Response:
        """Ротировать refresh-токен и выдать новый access.

        При недействительной сессии ответ 401 сразу удаляет refresh-cookie: иначе PWA
        продолжала бы слать мёртвый токен.
        """
        try:
            tokens = await self._mediator.send(RefreshSession(refresh))
        except (InvalidSessionError, SessionReuseError) as error:
            failure = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": {"code": error.code, "message": str(error)}},
            )
            self._cookies.clear_refresh(failure)
            return failure
        return self._session_response(response, tokens)

    async def logout(self, response: Response, refresh: RefreshCookie = None) -> Response:
        """Отозвать сессию и удалить cookie."""
        await self._mediator.send(RevokeSession(refresh))
        result = Response(status_code=status.HTTP_204_NO_CONTENT)
        self._cookies.clear_refresh(result)
        return result

    def _session_response(self, response: Response, tokens: SessionTokens) -> SessionResponse:
        """Установить refresh-cookie (если токен ротирован) и вернуть access."""
        if tokens.refresh_token is not None:
            self._cookies.set_refresh(
                response, tokens.refresh_token, tokens.refresh_expires_at, self._clock.now()
            )
        return SessionResponse(
            account_id=tokens.account_id,
            access_token=tokens.access_token,
            expires_at=tokens.access_expires_at,
        )
