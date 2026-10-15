"""Тесты доменной модели Identity."""

from __future__ import annotations

import random
from datetime import timedelta
from uuid import uuid4

import pytest

from beauty.contexts.identity.domain.auth_challenge import AuthChallenge, ChallengeStatus
from beauty.contexts.identity.domain.client_account import ClientAccount
from beauty.contexts.identity.domain.client_session import ClientSession, RotationOutcome
from beauty.contexts.identity.domain.errors import (
    BrowserSecretMismatch,
    ChallengeAlreadyClaimed,
    ChallengeExpired,
    ChallengeForeignUser,
    InvalidChallengeState,
    InvalidPhoneNumber,
    InvalidTelegramUserId,
    SessionInactive,
)
from beauty.contexts.identity.domain.events import (
    AuthChallengeCompleted,
    AuthChallengeRejected,
    ClientAuthenticated,
    ClientPhoneChanged,
    ClientRegistered,
    ClientSessionRevoked,
    ClientTelegramRelinked,
)
from beauty.contexts.identity.domain.services import ConfirmationCodeGenerator
from beauty.contexts.identity.domain.specifications import ContactOwnedBySender
from beauty.contexts.identity.domain.value_objects import (
    AuthNonce,
    ConfirmationCode,
    PhoneNumber,
    TelegramContact,
    TelegramUserId,
)
from beauty.shared.domain.secrets import HashedSecret
from tests.fakes import FrozenClock

ALICE = TelegramUserId(1001)
MALLORY = TelegramUserId(6666)
SECRET = "browser-secret"


def make_challenge(clock: FrozenClock, code: str = "42") -> AuthChallenge:
    """Challenge в состоянии PENDING с TTL 5 минут."""
    return AuthChallenge.start(
        challenge_id=uuid4(),
        nonce=AuthNonce("n" * 32),
        browser_secret=HashedSecret.of(SECRET),
        confirmation_code=ConfirmationCode(code),
        now=clock.now(),
        ttl=timedelta(minutes=5),
    )


class TestPhoneNumber:
    """Нормализация телефона."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("77011234567", "+77011234567"),
            ("+7 (701) 123-45-67", "+77011234567"),
            ("87011234567", "+77011234567"),
            ("+998 90 123 45 67", "+998901234567"),
        ],
    )
    def test_from_raw(self, raw: str, expected: str) -> None:
        """Telegram и ручной ввод приводятся к E.164."""
        assert PhoneNumber.from_raw(raw).value == expected

    @pytest.mark.parametrize("raw", ["", "123", "+0123456789", "phone"])
    def test_invalid(self, raw: str) -> None:
        """Мусор отвергается."""
        with pytest.raises(InvalidPhoneNumber):
            PhoneNumber.from_raw(raw)

    def test_masking_and_suffix(self) -> None:
        """Маска и поиск по последним цифрам («Дарья, номер на 8967»)."""
        phone = PhoneNumber("+77011238967")
        assert phone.masked() == "+7•••••8967"
        assert phone.ends_with("8967")
        assert not phone.ends_with("")

    def test_telegram_user_id_positive(self) -> None:
        """Telegram id положительный."""
        with pytest.raises(InvalidTelegramUserId):
            TelegramUserId(0)


class TestContactSpecification:
    """Защита от чужого контакта."""

    def test_own_contact(self) -> None:
        """Свой контакт принимается."""
        assert ContactOwnedBySender().is_satisfied_by(TelegramContact(ALICE, ALICE.value, "77011234567"))

    @pytest.mark.parametrize("contact_user_id", [MALLORY.value, None])
    def test_foreign_or_unknown_contact(self, contact_user_id: int | None) -> None:
        """Чужой контакт или контакт без аккаунта — отказ."""
        assert not ContactOwnedBySender().is_satisfied_by(
            TelegramContact(ALICE, contact_user_id, "77011234567")
        )


class TestAuthChallenge:
    """Машина состояний входа."""

    def test_happy_path(self, clock: FrozenClock) -> None:
        """PENDING → CLAIMED → CONFIRMED → COMPLETED → CONSUMED."""
        challenge = make_challenge(clock)
        account_id = uuid4()
        challenge.claim(ALICE, clock.now())
        assert challenge.confirm_code(ALICE, ConfirmationCode("42"), clock.now())
        challenge.complete(ALICE, account_id, clock.now())
        events = challenge.pull_events()
        assert [type(event) for event in events] == [AuthChallengeCompleted]
        assert challenge.consume(SECRET, clock.now()) == account_id
        assert challenge.status is ChallengeStatus.CONSUMED

    def test_claim_is_idempotent_for_same_user(self, clock: FrozenClock) -> None:
        """Повторный /start тем же пользователем не ломает вход."""
        challenge = make_challenge(clock)
        challenge.claim(ALICE, clock.now())
        challenge.claim(ALICE, clock.now())
        assert challenge.status is ChallengeStatus.CLAIMED

    def test_claim_by_another_user_rejected(self, clock: FrozenClock) -> None:
        """Ссылку нельзя «перехватить» другим аккаунтом Telegram."""
        challenge = make_challenge(clock)
        challenge.claim(ALICE, clock.now())
        with pytest.raises(ChallengeAlreadyClaimed):
            challenge.claim(MALLORY, clock.now())

    def test_wrong_code_rejects_irreversibly(self, clock: FrozenClock) -> None:
        """Неверный код — вход отклонён и не может быть продолжен."""
        challenge = make_challenge(clock, code="42")
        challenge.claim(ALICE, clock.now())
        assert not challenge.confirm_code(ALICE, ConfirmationCode("17"), clock.now())
        assert challenge.status is ChallengeStatus.REJECTED
        assert isinstance(challenge.pull_events()[0], AuthChallengeRejected)
        with pytest.raises(InvalidChallengeState):
            challenge.confirm_code(ALICE, ConfirmationCode("42"), clock.now())

    def test_foreign_user_cannot_confirm(self, clock: FrozenClock) -> None:
        """Сверка только тем, кто закрепил вход."""
        challenge = make_challenge(clock)
        challenge.claim(ALICE, clock.now())
        with pytest.raises(ChallengeForeignUser):
            challenge.confirm_code(MALLORY, ConfirmationCode("42"), clock.now())

    def test_cannot_complete_without_confirmation(self, clock: FrozenClock) -> None:
        """Контакт без сверки кода не завершает вход."""
        challenge = make_challenge(clock)
        challenge.claim(ALICE, clock.now())
        with pytest.raises(InvalidChallengeState):
            challenge.complete(ALICE, uuid4(), clock.now())

    def test_expiry(self, clock: FrozenClock) -> None:
        """После TTL операции запрещены, эффективный статус — expired."""
        challenge = make_challenge(clock)
        clock.advance(timedelta(minutes=5))
        assert challenge.effective_status(clock.now()) is ChallengeStatus.EXPIRED
        with pytest.raises(ChallengeExpired):
            challenge.claim(ALICE, clock.now())

    def test_consume_requires_browser_secret_and_is_single_use(self, clock: FrozenClock) -> None:
        """Сессию получает только начавший браузер, и только один раз."""
        challenge = make_challenge(clock)
        challenge.claim(ALICE, clock.now())
        challenge.confirm_code(ALICE, ConfirmationCode("42"), clock.now())
        challenge.complete(ALICE, uuid4(), clock.now())
        with pytest.raises(BrowserSecretMismatch):
            challenge.consume("attacker-guess", clock.now())
        challenge.consume(SECRET, clock.now())
        with pytest.raises(InvalidChallengeState):
            challenge.consume(SECRET, clock.now())


class TestClientAccount:
    """Учётная запись."""

    def test_register_and_authenticate_emit_events(self, clock: FrozenClock) -> None:
        """Регистрация и вход — события для других контекстов."""
        account = ClientAccount.register(
            account_id=uuid4(), phone=PhoneNumber("+77011234567"), telegram_user_id=ALICE, now=clock.now()
        )
        account.authenticate(clock.now())
        assert [type(event) for event in account.pull_events()] == [ClientRegistered, ClientAuthenticated]

    def test_change_phone_and_relink_are_idempotent(self, clock: FrozenClock) -> None:
        """Повтор того же значения не порождает событий."""
        account = ClientAccount.register(
            account_id=uuid4(), phone=PhoneNumber("+77011234567"), telegram_user_id=ALICE, now=clock.now()
        )
        account.pull_events()
        account.change_phone(PhoneNumber("+77011234567"), clock.now())
        account.relink_telegram(ALICE, clock.now())
        assert account.pull_events() == []
        account.change_phone(PhoneNumber("+77019999999"), clock.now())
        account.relink_telegram(MALLORY, clock.now())
        assert [type(event) for event in account.pull_events()] == [
            ClientPhoneChanged,
            ClientTelegramRelinked,
        ]


class TestClientSession:
    """Ротация refresh-токена."""

    def _session(self, clock: FrozenClock) -> ClientSession:
        return ClientSession.open(
            session_id=uuid4(),
            account_id=uuid4(),
            refresh_secret=HashedSecret.of("r1"),
            now=clock.now(),
            ttl=timedelta(days=30),
        )

    def test_rotation_slides_expiry(self, clock: FrozenClock) -> None:
        """Ротация меняет секрет и продлевает срок."""
        session = self._session(clock)
        clock.advance(timedelta(days=10))
        assert (
            session.rotate("r1", HashedSecret.of("r2"), clock.now(), timedelta(days=30))
            is RotationOutcome.ROTATED
        )
        assert session.refresh_secret.matches("r2")
        assert session.expires_at == clock.now() + timedelta(days=30)

    def test_concurrent_refresh_within_grace(self, clock: FrozenClock) -> None:
        """Вторая вкладка с только что заменённым токеном — не кража."""
        session = self._session(clock)
        session.rotate("r1", HashedSecret.of("r2"), clock.now(), timedelta(days=30))
        clock.advance(timedelta(seconds=5))
        outcome = session.rotate("r1", HashedSecret.of("r3"), clock.now(), timedelta(days=30))
        assert outcome is RotationOutcome.CONCURRENT
        assert session.refresh_secret.matches("r2")
        assert session.revoked_at is None

    def test_reuse_after_grace_revokes(self, clock: FrozenClock) -> None:
        """Старый токен после окна снисхождения — признак кражи: сессия отозвана."""
        session = self._session(clock)
        session.rotate("r1", HashedSecret.of("r2"), clock.now(), timedelta(days=30))
        clock.advance(timedelta(minutes=5))
        outcome = session.rotate("r1", HashedSecret.of("r3"), clock.now(), timedelta(days=30))
        assert outcome is RotationOutcome.REUSE_DETECTED
        assert session.revoked_at == clock.now()
        assert isinstance(session.pull_events()[-1], ClientSessionRevoked)
        with pytest.raises(SessionInactive):
            session.rotate("r2", HashedSecret.of("r4"), clock.now(), timedelta(days=30))


class TestConfirmationCodeGenerator:
    """Number matching."""

    def test_options_contain_code_exactly_once(self) -> None:
        """Ровно один верный вариант среди уникальных."""
        generator = ConfirmationCodeGenerator(random.Random(7))
        for _ in range(200):
            code = generator.generate()
            options = [option.value for option in generator.options_for(code)]
            assert options.count(code.value) == 1
            assert len(set(options)) == 3
            assert all(len(option) == 2 for option in options)
