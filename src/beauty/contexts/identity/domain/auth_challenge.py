"""Агрегат ``AuthChallenge`` — одна попытка входа через Telegram.

Машина состояний::

    PENDING ──claim──▶ CLAIMED ──confirm_code──▶ CONFIRMED ──complete──▶ COMPLETED ──consume──▶ CONSUMED
                          │            (неверный код)
                          └──────────────▶ REJECTED

* ``claim`` — пользователь Telegram открыл deep link; challenge закрепляется за ним,
  и никто другой этот вход продолжить не может;
* ``confirm_code`` — пользователь выбрал в боте код с экрана браузера (number
  matching). Это защищает от фишинга: злоумышленник не может прислать жертве свою
  ссылку на вход, потому что жертва не видит код на экране злоумышленника;
* ``complete`` — пользователь поделился своим контактом, учётная запись найдена;
* ``consume`` — браузер, начавший вход (у него секрет из httpOnly-cookie), обменял
  challenge на сессию. Обмен одноразовый.

Истечение срока не хранится отдельной транзакцией: оно вычисляется от ``expires_at``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from beauty.contexts.identity.domain.errors import (
    BrowserSecretMismatch,
    ChallengeAlreadyClaimed,
    ChallengeExpired,
    ChallengeForeignUser,
    InvalidChallengeState,
)
from beauty.contexts.identity.domain.events import AuthChallengeCompleted, AuthChallengeRejected
from beauty.contexts.identity.domain.value_objects import AuthNonce, ConfirmationCode, TelegramUserId
from beauty.shared.domain.aggregate import AggregateRoot
from beauty.shared.domain.secrets import HashedSecret


class ChallengeStatus(StrEnum):
    """Шаги входа."""

    PENDING = "pending"
    CLAIMED = "claimed"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CONSUMED = "consumed"
    REJECTED = "rejected"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        """Вход завершён (успешно или нет) и больше не изменится."""
        return self in {ChallengeStatus.CONSUMED, ChallengeStatus.REJECTED, ChallengeStatus.EXPIRED}

    @property
    def is_in_progress(self) -> bool:
        """Вход ещё идёт и может истечь."""
        return self in {ChallengeStatus.PENDING, ChallengeStatus.CLAIMED, ChallengeStatus.CONFIRMED}


class AuthChallenge(AggregateRoot):
    """Попытка входа клиента."""

    def __init__(
        self,
        challenge_id: UUID,
        nonce: AuthNonce,
        browser_secret: HashedSecret,
        confirmation_code: ConfirmationCode,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        """Создать challenge в состоянии ``PENDING`` (используйте ``start``)."""
        self.id = challenge_id
        self.nonce = nonce
        self.browser_secret = browser_secret
        self.confirmation_code = confirmation_code
        self.status = ChallengeStatus.PENDING
        self.telegram_user_id: TelegramUserId | None = None
        self.account_id: UUID | None = None
        self.created_at = created_at
        self.expires_at = expires_at
        self.completed_at: datetime | None = None
        self.consumed_at: datetime | None = None

    @classmethod
    def start(
        cls,
        *,
        challenge_id: UUID,
        nonce: AuthNonce,
        browser_secret: HashedSecret,
        confirmation_code: ConfirmationCode,
        now: datetime,
        ttl: timedelta,
    ) -> AuthChallenge:
        """Начать вход."""
        if ttl <= timedelta(0):
            raise ValueError("TTL входа должен быть положительным")
        return cls(challenge_id, nonce, browser_secret, confirmation_code, now, now + ttl)

    def is_expired(self, now: datetime) -> bool:
        """Истёк ли срок входа."""
        return now >= self.expires_at

    def effective_status(self, now: datetime) -> ChallengeStatus:
        """Статус с учётом истечения срока (для чтения)."""
        if self.status.is_in_progress and self.is_expired(now):
            return ChallengeStatus.EXPIRED
        return self.status

    def claim(self, telegram_user: TelegramUserId, now: datetime) -> None:
        """Закрепить вход за пользователем Telegram (идемпотентно для того же пользователя)."""
        self._ensure_not_expired(now)
        if self.status is ChallengeStatus.PENDING:
            self.telegram_user_id = telegram_user
            self.status = ChallengeStatus.CLAIMED
            return
        if self.telegram_user_id != telegram_user:
            raise ChallengeAlreadyClaimed()
        if self.status not in {ChallengeStatus.CLAIMED, ChallengeStatus.CONFIRMED}:
            raise InvalidChallengeState()

    def confirm_code(self, telegram_user: TelegramUserId, code: ConfirmationCode, now: datetime) -> bool:
        """Сверить код; при несовпадении вход отклоняется безвозвратно.

        Возвращает ``True``, если код верный. Метод не бросает исключение на неверный
        код: отклонение — это изменение состояния, которое должно сохраниться.
        """
        self._ensure_owner(telegram_user)
        self._ensure_not_expired(now)
        self._ensure_status(ChallengeStatus.CLAIMED)
        if code != self.confirmation_code:
            self.status = ChallengeStatus.REJECTED
            self._record(AuthChallengeRejected(occurred_at=now, challenge_id=self.id, reason="code_mismatch"))
            return False
        self.status = ChallengeStatus.CONFIRMED
        return True

    def confirm_implicitly(self, telegram_user: TelegramUserId, now: datetime) -> None:
        """Подтвердить без сверки кода (политика ``implicit``, например для dev)."""
        self._ensure_owner(telegram_user)
        self._ensure_not_expired(now)
        if self.status is ChallengeStatus.CONFIRMED:
            return
        self._ensure_status(ChallengeStatus.CLAIMED)
        self.status = ChallengeStatus.CONFIRMED

    def complete(self, telegram_user: TelegramUserId, account_id: UUID, now: datetime) -> None:
        """Завершить вход найденной учётной записью."""
        self._ensure_owner(telegram_user)
        self._ensure_not_expired(now)
        self._ensure_status(ChallengeStatus.CONFIRMED)
        self.account_id = account_id
        self.status = ChallengeStatus.COMPLETED
        self.completed_at = now
        self._record(AuthChallengeCompleted(occurred_at=now, challenge_id=self.id))

    def consume(self, raw_browser_secret: str, now: datetime) -> UUID:
        """Обменять завершённый вход на учётную запись (один раз, только начавшим браузером)."""
        if not self.browser_secret.matches(raw_browser_secret):
            raise BrowserSecretMismatch()
        self._ensure_not_expired(now)
        self._ensure_status(ChallengeStatus.COMPLETED)
        if self.account_id is None:  # pragma: no cover - инвариант complete()
            raise InvalidChallengeState("Вход завершён без учётной записи")
        self.status = ChallengeStatus.CONSUMED
        self.consumed_at = now
        return self.account_id

    def owned_by_browser(self, raw_browser_secret: str) -> bool:
        """Начат ли вход в браузере с этим секретом."""
        return self.browser_secret.matches(raw_browser_secret)

    def _ensure_not_expired(self, now: datetime) -> None:
        """Запретить операции после истечения срока."""
        if self.is_expired(now):
            raise ChallengeExpired()

    def _ensure_owner(self, telegram_user: TelegramUserId) -> None:
        """Продолжать вход может только закрепивший его пользователь."""
        if self.telegram_user_id != telegram_user:
            raise ChallengeForeignUser()

    def _ensure_status(self, *allowed: ChallengeStatus) -> None:
        """Проверить, что вход на нужном шаге."""
        if self.status not in allowed:
            raise InvalidChallengeState(f"Шаг {self.status.value} не допускает операцию")
