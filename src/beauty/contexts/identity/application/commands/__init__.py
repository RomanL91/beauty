"""Команды Identity — по модулю на сценарий: сообщение + его обработчик."""

from beauty.contexts.identity.application.commands.block_account import (
    SetAccountBlocked,
    SetAccountBlockedHandler,
)
from beauty.contexts.identity.application.commands.claim_challenge import (
    ClaimChallenge,
    ClaimChallengeHandler,
)
from beauty.contexts.identity.application.commands.complete_with_contact import (
    CompleteChallengeWithContact,
    CompleteChallengeWithContactHandler,
)
from beauty.contexts.identity.application.commands.confirm_code import (
    ConfirmChallengeCode,
    ConfirmChallengeCodeHandler,
)
from beauty.contexts.identity.application.commands.exchange_challenge import (
    ExchangeChallengeForSession,
    ExchangeChallengeForSessionHandler,
)
from beauty.contexts.identity.application.commands.refresh_session import (
    RefreshSession,
    RefreshSessionHandler,
)
from beauty.contexts.identity.application.commands.revoke_session import RevokeSession, RevokeSessionHandler
from beauty.contexts.identity.application.commands.start_telegram_auth import (
    StartTelegramAuth,
    StartTelegramAuthHandler,
)

__all__ = [
    "ClaimChallenge",
    "ClaimChallengeHandler",
    "CompleteChallengeWithContact",
    "CompleteChallengeWithContactHandler",
    "ConfirmChallengeCode",
    "ConfirmChallengeCodeHandler",
    "ExchangeChallengeForSession",
    "ExchangeChallengeForSessionHandler",
    "RefreshSession",
    "RefreshSessionHandler",
    "RevokeSession",
    "RevokeSessionHandler",
    "SetAccountBlocked",
    "SetAccountBlockedHandler",
    "StartTelegramAuth",
    "StartTelegramAuthHandler",
]
