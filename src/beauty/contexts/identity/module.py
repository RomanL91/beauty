"""Модуль контекста Identity: сборка зависимостей и регистрация в приложении.

Модуль — единственное место, где Identity «знает» о своей инфраструктуре. Корень
композиции создаёт модуль, передаёт ему общие зависимости, а модуль регистрирует
обработчики в медиаторе, коды ошибок в HTTP-маппере и отдаёт роутеры API и бота.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Router
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beauty.contexts.identity.application.commands import (
    ClaimChallenge,
    ClaimChallengeHandler,
    CompleteChallengeWithContact,
    CompleteChallengeWithContactHandler,
    ConfirmChallengeCode,
    ConfirmChallengeCodeHandler,
    ExchangeChallengeForSession,
    ExchangeChallengeForSessionHandler,
    RefreshSession,
    RefreshSessionHandler,
    RevokeSession,
    RevokeSessionHandler,
    StartTelegramAuth,
    StartTelegramAuthHandler,
)
from beauty.contexts.identity.application.queries import GetChallengeStatus, GetChallengeStatusHandler
from beauty.contexts.identity.application.services.account_resolution import AccountResolver
from beauty.contexts.identity.application.services.confirmation import ConfirmationPolicyFactory
from beauty.contexts.identity.domain.services import ConfirmationCodeGenerator
from beauty.contexts.identity.infrastructure.mapping import IdentityOrmMapper
from beauty.contexts.identity.infrastructure.readers import SqlChallengeStatusReader
from beauty.contexts.identity.infrastructure.realtime import AuthChallengeTopicResolver
from beauty.contexts.identity.infrastructure.telegram import TelegramDeepLinkBuilder
from beauty.contexts.identity.infrastructure.tokens import (
    JwtAccessTokenIssuer,
    JwtAccessTokenVerifier,
    UrlSafeSecretGenerator,
)
from beauty.contexts.identity.infrastructure.uow import SqlAlchemyIdentityUnitOfWork
from beauty.contexts.identity.presentation.api.controller import IdentityApiController
from beauty.contexts.identity.presentation.api.cookies import AuthCookiePolicy
from beauty.contexts.identity.presentation.bot.controller import TelegramAuthBotController
from beauty.contexts.identity.presentation.bot.errors import BotErrorPresenter
from beauty.contexts.identity.presentation.bot.keyboards import AuthKeyboards
from beauty.contexts.identity.presentation.bot.renderers import ClaimStepRenderers
from beauty.contexts.identity.presentation.bot.texts import BotTexts
from beauty.shared.application.mediator import Mediator
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator
from beauty.shared.infrastructure.config import AuthSettings, HttpSettings, TelegramSettings
from beauty.shared.infrastructure.outbox.writer import OutboxWriter
from beauty.shared.infrastructure.realtime.bridge import TopicResolver
from beauty.shared.infrastructure.realtime.hub import RealtimeHub
from beauty.shared.infrastructure.web.errors import HttpErrorMapper

_HTTP_STATUSES: dict[str, int] = {
    "challenge_not_found": 404,
    "no_challenge_awaiting_contact": 404,
    "challenge_expired": 410,
    "challenge_already_claimed": 409,
    "invalid_challenge_state": 409,
    "challenge_foreign_user": 403,
    "browser_secret_mismatch": 404,
    "invalid_session": 401,
    "session_reuse_detected": 401,
    "session_inactive": 401,
    "identity_conflict": 409,
    "contact_not_owned": 422,
    "invalid_phone": 422,
    "invalid_nonce": 422,
}


@dataclass(frozen=True, slots=True)
class IdentityDependencies:
    """Общие зависимости, которые модуль получает от корня композиции."""

    session_factory: async_sessionmaker[AsyncSession]
    outbox_writer: OutboxWriter
    clock: Clock
    id_generator: IdGenerator
    hub: RealtimeHub
    auth: AuthSettings
    telegram: TelegramSettings
    http: HttpSettings


class IdentityModule:
    """Сборка контекста Identity."""

    def __init__(self, dependencies: IdentityDependencies) -> None:
        """Создать долгоживущие (stateless) компоненты контекста."""
        IdentityOrmMapper.map()
        self._deps = dependencies
        self._secrets = UrlSafeSecretGenerator()
        self._policy = ConfirmationPolicyFactory().create(
            dependencies.auth.confirmation_policy, ConfirmationCodeGenerator()
        )
        self._deep_links = TelegramDeepLinkBuilder(dependencies.telegram.bot_username)
        jwt_secret = dependencies.auth.jwt_secret.get_secret_value()
        self._access_tokens = JwtAccessTokenIssuer(
            jwt_secret, dependencies.auth.jwt_issuer, dependencies.auth.access_ttl, dependencies.id_generator
        )
        self.access_token_verifier = JwtAccessTokenVerifier(
            jwt_secret, dependencies.auth.jwt_issuer, dependencies.clock
        )
        self._resolver = AccountResolver(dependencies.id_generator)
        self._status_reader = SqlChallengeStatusReader(dependencies.session_factory)

    def register(self, mediator: Mediator, http_errors: HttpErrorMapper) -> None:
        """Зарегистрировать обработчики и коды ошибок."""
        deps, auth = self._deps, self._deps.auth
        mediator.register(
            StartTelegramAuth,
            lambda: StartTelegramAuthHandler(
                self._uow(),
                deps.clock,
                deps.id_generator,
                self._secrets,
                self._policy,
                self._deep_links,
                auth.challenge_ttl,
            ),
        )
        mediator.register(
            ClaimChallenge, lambda: ClaimChallengeHandler(self._uow(), deps.clock, self._policy)
        )
        mediator.register(ConfirmChallengeCode, lambda: ConfirmChallengeCodeHandler(self._uow(), deps.clock))
        mediator.register(
            CompleteChallengeWithContact,
            lambda: CompleteChallengeWithContactHandler(self._uow(), deps.clock, self._resolver),
        )
        mediator.register(
            ExchangeChallengeForSession,
            lambda: ExchangeChallengeForSessionHandler(
                self._uow(),
                deps.clock,
                deps.id_generator,
                self._secrets,
                self._access_tokens,
                auth.refresh_ttl,
            ),
        )
        mediator.register(
            RefreshSession,
            lambda: RefreshSessionHandler(
                self._uow(), deps.clock, self._secrets, self._access_tokens, auth.refresh_ttl
            ),
        )
        mediator.register(RevokeSession, lambda: RevokeSessionHandler(self._uow(), deps.clock))
        mediator.register(
            GetChallengeStatus, lambda: GetChallengeStatusHandler(self._status_reader, deps.clock)
        )
        for code, status in _HTTP_STATUSES.items():
            http_errors.register(code, status)

    def api_router(self, mediator: Mediator) -> APIRouter:
        """HTTP-роутер Identity."""
        cookies = AuthCookiePolicy(
            api_prefix=self._deps.http.api_prefix,
            challenge_ttl=self._deps.auth.challenge_ttl,
            secure=self._deps.auth.cookie_secure,
            domain=self._deps.auth.cookie_domain,
        )
        controller = IdentityApiController(
            mediator,
            self._deps.hub,
            cookies,
            self._deps.clock,
            stream_poll_interval=self._deps.http.sse_poll_interval,
            stream_max_duration=self._deps.auth.challenge_ttl.total_seconds() + 30,
        )
        return controller.router()

    def bot_router(self, mediator: Mediator) -> Router:
        """Роутер aiogram бота авторизации."""
        keyboards = AuthKeyboards()
        controller = TelegramAuthBotController(
            mediator,
            keyboards,
            ClaimStepRenderers(keyboards),
            BotErrorPresenter(BotTexts.ERRORS, BotTexts.FALLBACK_ERROR),
        )
        return controller.router()

    def realtime_resolvers(self) -> tuple[TopicResolver, ...]:
        """Резолверы realtime-топиков Identity."""
        return (AuthChallengeTopicResolver(),)

    def _uow(self) -> SqlAlchemyIdentityUnitOfWork:
        """Новый Unit of Work на каждый обработчик."""
        return SqlAlchemyIdentityUnitOfWork(self._deps.session_factory, self._deps.outbox_writer)
