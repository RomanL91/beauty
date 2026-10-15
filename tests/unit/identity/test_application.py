"""Сценарии Identity через медиатор на in-memory Unit of Work."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

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
from beauty.contexts.identity.application.dto import ClaimStep, SessionTokens, StartedChallenge
from beauty.contexts.identity.application.errors import (
    ChallengeNotFoundError,
    IdentityConflictError,
    InvalidSessionError,
    NoChallengeAwaitingContactError,
    SessionReuseError,
)
from beauty.contexts.identity.application.services.account_resolution import AccountResolver
from beauty.contexts.identity.application.services.confirmation import ConfirmationPolicyFactory
from beauty.contexts.identity.application.services.refresh_token import RefreshToken
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.errors import (
    BrowserSecretMismatch,
    ContactNotOwnedBySender,
    InvalidChallengeState,
)
from beauty.contexts.identity.domain.events import ClientAuthenticated, ClientRegistered
from beauty.contexts.identity.domain.services import ConfirmationCodeGenerator
from beauty.contexts.identity.domain.value_objects import PhoneNumber, TelegramUserId
from beauty.contexts.identity.infrastructure.telegram import TelegramDeepLinkBuilder
from beauty.contexts.identity.infrastructure.tokens import JwtAccessTokenIssuer, JwtAccessTokenVerifier
from beauty.shared.application.mediator import Mediator
from beauty.shared.domain.ids import default_id_generator
from tests.fakes import CountingSecretGenerator, FrozenClock, IdentityStore, InMemoryIdentityUnitOfWork

ALICE = 1001
PHONE = "77011234567"


class IdentityHarness:
    """Медиатор Identity, собранный на in-memory хранилище."""

    def __init__(self, clock: FrozenClock, policy: str = "number_matching") -> None:
        """Собрать медиатор."""
        self.clock = clock
        self.store = IdentityStore()
        secrets = CountingSecretGenerator()
        policy_impl = ConfirmationPolicyFactory().create(policy, ConfirmationCodeGenerator())
        issuer = JwtAccessTokenIssuer("k" * 32, "beauty", timedelta(minutes=15), default_id_generator)
        self.verifier = JwtAccessTokenVerifier("k" * 32, "beauty", clock)
        resolver = AccountResolver(default_id_generator)
        mediator = Mediator()
        mediator.register(
            StartTelegramAuth,
            lambda: StartTelegramAuthHandler(
                self._uow(),
                clock,
                default_id_generator,
                secrets,
                policy_impl,
                TelegramDeepLinkBuilder("@beauty_bot"),
                timedelta(minutes=5),
            ),
        )
        mediator.register(ClaimChallenge, lambda: ClaimChallengeHandler(self._uow(), clock, policy_impl))
        mediator.register(ConfirmChallengeCode, lambda: ConfirmChallengeCodeHandler(self._uow(), clock))
        mediator.register(
            CompleteChallengeWithContact,
            lambda: CompleteChallengeWithContactHandler(self._uow(), clock, resolver),
        )
        mediator.register(
            ExchangeChallengeForSession,
            lambda: ExchangeChallengeForSessionHandler(
                self._uow(), clock, default_id_generator, secrets, issuer, timedelta(days=30)
            ),
        )
        mediator.register(
            RefreshSession,
            lambda: RefreshSessionHandler(self._uow(), clock, secrets, issuer, timedelta(days=30)),
        )
        mediator.register(RevokeSession, lambda: RevokeSessionHandler(self._uow(), clock))
        self.mediator = mediator

    def _uow(self) -> InMemoryIdentityUnitOfWork:
        return InMemoryIdentityUnitOfWork(self.store)

    @staticmethod
    def nonce_of(started: StartedChallenge) -> str:
        """Достать nonce из deep link."""
        return started.deep_link.rsplit("start=", 1)[1]

    async def login(self, telegram_user: int = ALICE, phone: str = PHONE) -> SessionTokens:
        """Пройти весь вход."""
        started = await self.mediator.send(StartTelegramAuth())
        nonce = self.nonce_of(started)
        claim = await self.mediator.send(ClaimChallenge(nonce, telegram_user))
        if claim.step is ClaimStep.ASK_CODE:
            confirmed = await self.mediator.send(
                ConfirmChallengeCode(nonce, telegram_user, started.confirmation_code)
            )
            assert confirmed.accepted
        await self.mediator.send(CompleteChallengeWithContact(telegram_user, telegram_user, phone))
        return await self.mediator.send(
            ExchangeChallengeForSession(started.challenge_id, started.browser_secret)
        )


@pytest.fixture
def harness(clock: FrozenClock) -> IdentityHarness:
    """Медиатор с политикой number matching."""
    return IdentityHarness(clock)


async def test_full_login_issues_valid_tokens(harness: IdentityHarness) -> None:
    """Вход создаёт клиента, события и токены, access-токен проверяем."""
    tokens = await harness.login()
    claims = harness.verifier.verify(tokens.access_token)
    assert claims.account_id == tokens.account_id
    assert RefreshToken.decode(tokens.refresh_token).session_id == claims.session_id
    kinds = [type(event) for event in harness.store.events]
    assert ClientRegistered in kinds
    assert ClientAuthenticated in kinds


async def test_number_matching_offers_options_with_correct_code(harness: IdentityHarness) -> None:
    """Бот получает три варианта, один из которых — код браузера."""
    started = await harness.mediator.send(StartTelegramAuth())
    claim = await harness.mediator.send(ClaimChallenge(harness.nonce_of(started), ALICE))
    assert claim.step is ClaimStep.ASK_CODE
    assert started.confirmation_code in claim.code_options
    assert len(claim.code_options) == 3
    assert started.deep_link.startswith("https://t.me/beauty_bot?start=")


async def test_wrong_code_blocks_login(harness: IdentityHarness) -> None:
    """Фишинговая ссылка: жертва не знает код — вход отклоняется, контакт не принимается."""
    started = await harness.mediator.send(StartTelegramAuth())
    nonce = harness.nonce_of(started)
    claim = await harness.mediator.send(ClaimChallenge(nonce, ALICE))
    wrong = next(option for option in claim.code_options if option != started.confirmation_code)
    result = await harness.mediator.send(ConfirmChallengeCode(nonce, ALICE, wrong))
    assert not result.accepted
    with pytest.raises(NoChallengeAwaitingContactError):
        await harness.mediator.send(CompleteChallengeWithContact(ALICE, ALICE, PHONE))


async def test_implicit_policy_skips_code(clock: FrozenClock) -> None:
    """Политика implicit сразу просит контакт."""
    harness = IdentityHarness(clock, policy="implicit")
    started = await harness.mediator.send(StartTelegramAuth())
    claim = await harness.mediator.send(ClaimChallenge(harness.nonce_of(started), ALICE))
    assert claim.step is ClaimStep.ASK_CONTACT


async def test_foreign_contact_rejected(harness: IdentityHarness) -> None:
    """Пересланный чужой контакт не принимается."""
    with pytest.raises(ContactNotOwnedBySender):
        await harness.mediator.send(CompleteChallengeWithContact(ALICE, 777, PHONE))


async def test_unknown_nonce(harness: IdentityHarness) -> None:
    """Несуществующий вход."""
    with pytest.raises(ChallengeNotFoundError):
        await harness.mediator.send(ClaimChallenge("z" * 32, ALICE))


async def test_second_login_reuses_account(harness: IdentityHarness) -> None:
    """Повторный вход — та же учётная запись."""
    first = await harness.login()
    second = await harness.login()
    assert first.account_id == second.account_id
    assert len(harness.store.accounts) == 1


async def test_new_telegram_account_same_phone_relinks(harness: IdentityHarness) -> None:
    """Новый аккаунт Telegram на тот же номер — та же учётная запись, Telegram перепривязан."""
    first = await harness.login(telegram_user=ALICE)
    second = await harness.login(telegram_user=2002)
    assert first.account_id == second.account_id
    assert harness.store.accounts[first.account_id].telegram_user_id == TelegramUserId(2002)


async def test_phone_taken_by_another_account_is_conflict(harness: IdentityHarness) -> None:
    """Смена номера на номер другого клиента — конфликт для поддержки."""
    await harness.login(telegram_user=ALICE, phone="77011111111")
    await harness.login(telegram_user=2002, phone="77012222222")
    with pytest.raises(IdentityConflictError):
        await harness.login(telegram_user=ALICE, phone="77012222222")


async def test_exchange_is_single_use_and_bound_to_browser(harness: IdentityHarness) -> None:
    """Обмен одноразовый и требует секрет браузера."""
    started = await harness.mediator.send(StartTelegramAuth())
    nonce = harness.nonce_of(started)
    await harness.mediator.send(ClaimChallenge(nonce, ALICE))
    await harness.mediator.send(ConfirmChallengeCode(nonce, ALICE, started.confirmation_code))
    await harness.mediator.send(CompleteChallengeWithContact(ALICE, ALICE, PHONE))
    with pytest.raises(BrowserSecretMismatch):
        await harness.mediator.send(
            ExchangeChallengeForSession(started.challenge_id, "stolen-nonce-not-secret")
        )
    await harness.mediator.send(ExchangeChallengeForSession(started.challenge_id, started.browser_secret))
    with pytest.raises(InvalidChallengeState):
        await harness.mediator.send(ExchangeChallengeForSession(started.challenge_id, started.browser_secret))


async def test_refresh_rotation_and_reuse_detection(harness: IdentityHarness, clock: FrozenClock) -> None:
    """Ротация работает; повтор старого токена вне окна — отзыв сессии."""
    tokens = await harness.login()
    rotated = await harness.mediator.send(RefreshSession(tokens.refresh_token))
    assert rotated.refresh_token is not None
    assert rotated.refresh_token != tokens.refresh_token
    clock.advance(timedelta(minutes=2))
    with pytest.raises(SessionReuseError):
        await harness.mediator.send(RefreshSession(tokens.refresh_token))
    with pytest.raises(InvalidSessionError):
        await harness.mediator.send(RefreshSession(rotated.refresh_token))


async def test_concurrent_tabs_refresh_without_revocation(harness: IdentityHarness) -> None:
    """Две вкладки с одним cookie: вторая получает access без новой ротации."""
    tokens = await harness.login()
    first = await harness.mediator.send(RefreshSession(tokens.refresh_token))
    second = await harness.mediator.send(RefreshSession(tokens.refresh_token))
    assert first.refresh_token is not None
    assert second.refresh_token is None
    assert harness.verifier.verify(second.access_token).account_id == tokens.account_id


@pytest.mark.parametrize("garbage", [None, "", "no-dot", "not-a-uuid.secret", f"{uuid4()}."])
async def test_refresh_with_garbage(harness: IdentityHarness, garbage: str | None) -> None:
    """Мусор в cookie — недействительная сессия."""
    with pytest.raises(InvalidSessionError):
        await harness.mediator.send(RefreshSession(garbage))


async def test_logout_revokes_and_is_idempotent(harness: IdentityHarness) -> None:
    """Выход отзывает сессию; повторный выход и мусор — без ошибок."""
    tokens = await harness.login()
    await harness.mediator.send(RevokeSession(tokens.refresh_token))
    await harness.mediator.send(RevokeSession(tokens.refresh_token))
    await harness.mediator.send(RevokeSession("garbage"))
    with pytest.raises(InvalidSessionError):
        await harness.mediator.send(RefreshSession(tokens.refresh_token))


async def test_account_resolution_registers_once(harness: IdentityHarness, clock: FrozenClock) -> None:
    """Регистрация ровно одна, остальные звенья находят существующую запись."""
    account = ClientAccount.register(
        account_id=uuid4(),
        phone=PhoneNumber("+77011234567"),
        telegram_user_id=TelegramUserId(ALICE),
        now=clock.now(),
    )
    harness.store.accounts[account.id] = account
    tokens = await harness.login()
    assert tokens.account_id == account.id


async def test_access_token_expiry_follows_clock(harness: IdentityHarness, clock: FrozenClock) -> None:
    """Истёкший по часам приложения access-токен отвергается."""
    tokens = await harness.login()
    clock.advance(timedelta(minutes=16))
    with pytest.raises(InvalidSessionError):
        harness.verifier.verify(tokens.access_token)
