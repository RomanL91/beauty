"""Таблицы схемы ``identity``.

Индексы подобраны под реальные запросы:

* ``auth_challenges.nonce`` (unique) — поиск входа по deep link;
* ``ix_auth_challenges_awaiting_contact`` — частичный индекс по
  ``(telegram_user_id, created_at DESC)`` только для ``confirmed``: запрос
  «последний вход пользователя, ждущий контакт» читает одну запись индекса;
* ``ix_auth_challenges_expiry`` — частичный по ``expires_at`` для незавершённых входов
  (очистка просроченных);
* ``client_sessions``: частичный индекс активных сессий учётной записи
  (отзыв всех сессий, список устройств).

Связей ORM (``relationship``) между агрегатами нет намеренно: агрегаты ссылаются друг
на друга только по id, поэтому ленивых подгрузок и N+1 нет по построению. Обратная
сторона — SQLAlchemy не знает порядка вставки разных агрегатов в одном flush, поэтому
внешние ключи между агрегатами объявлены ``DEFERRABLE INITIALLY DEFERRED``:
целостность проверяется при COMMIT, а не посреди flush.
"""

from __future__ import annotations

from operator import attrgetter

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import UUID

from beauty.contexts.identity.domain.auth_challenge import ChallengeStatus
from beauty.contexts.identity.domain.value_objects import (
    AuthNonce,
    ConfirmationCode,
    PhoneNumber,
    TelegramUserId,
)
from beauty.shared.domain.secrets import HashedSecret
from beauty.shared.infrastructure.db.metadata import metadata
from beauty.shared.infrastructure.db.types import BigIntegerValueObjectType, StringValueObjectType

SCHEMA = "identity"

_value = attrgetter("value")
PhoneNumberType = StringValueObjectType(PhoneNumber, _value)
TelegramUserIdType = BigIntegerValueObjectType(TelegramUserId, _value)
AuthNonceType = StringValueObjectType(AuthNonce, _value)
ConfirmationCodeType = StringValueObjectType(ConfirmationCode, _value)
HashedSecretType = StringValueObjectType(HashedSecret, attrgetter("digest"))

ChallengeStatusType = Enum(
    ChallengeStatus,
    name="challenge_status",
    native_enum=False,
    create_constraint=True,
    length=16,
    values_callable=lambda members: [member.value for member in members],
    validate_strings=True,
)

client_accounts = Table(
    "client_accounts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("phone", PhoneNumberType, nullable=False, unique=True),
    Column("telegram_user_id", TelegramUserIdType, nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("blocked_at", DateTime(timezone=True), comment="заблокирован хозяином сервиса"),
    Column("blocked_reason", Text),
    Column("last_authenticated_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    schema=SCHEMA,
    comment="Глобальные учётные записи клиентов",
)

auth_challenges = Table(
    "auth_challenges",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("nonce", AuthNonceType, nullable=False, unique=True),
    Column("browser_secret_digest", HashedSecretType, nullable=False),
    Column("confirmation_code", ConfirmationCodeType, nullable=False),
    Column("status", ChallengeStatusType, nullable=False),
    Column("telegram_user_id", TelegramUserIdType),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey(client_accounts.c.id, ondelete="CASCADE", deferrable=True, initially="DEFERRED"),
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("consumed_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    schema=SCHEMA,
    comment="Попытки входа через Telegram",
)

Index(
    "ix_auth_challenges_awaiting_contact",
    auth_challenges.c.telegram_user_id,
    auth_challenges.c.created_at.desc(),
    postgresql_where=text("status = 'confirmed'"),
)
Index(
    "ix_auth_challenges_expiry",
    auth_challenges.c.expires_at,
    postgresql_where=text("status IN ('pending', 'claimed', 'confirmed')"),
)
Index(
    "ix_auth_challenges_account_id",
    auth_challenges.c.account_id,
    postgresql_where=text("account_id IS NOT NULL"),
)

client_sessions = Table(
    "client_sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey(client_accounts.c.id, ondelete="CASCADE", deferrable=True, initially="DEFERRED"),
        nullable=False,
    ),
    Column("refresh_digest", HashedSecretType, nullable=False),
    Column("previous_refresh_digest", HashedSecretType),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("rotated_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("revoke_reason", Text),
    Column("version", Integer, nullable=False),
    schema=SCHEMA,
    comment="Сессии клиентов (refresh-токены хранятся хешами)",
)

Index(
    "ix_client_sessions_active_by_account",
    client_sessions.c.account_id,
    postgresql_where=text("revoked_at IS NULL"),
)
