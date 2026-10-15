"""Секреты и JWT access-токены."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from beauty.contexts.identity.application.errors import InvalidSessionError
from beauty.contexts.identity.application.ports import AccessToken, AccessTokenIssuer, SecretGenerator
from beauty.shared.domain.clock import Clock
from beauty.shared.domain.ids import IdGenerator


class UrlSafeSecretGenerator(SecretGenerator):
    """Секреты из CSPRNG ОС."""

    def token(self, nbytes: int = 32) -> str:
        """URL-safe base64 без паддинга."""
        return secrets.token_urlsafe(nbytes)


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """Проверенные утверждения access-токена."""

    account_id: UUID
    session_id: UUID
    kind: str


class JwtAccessTokenIssuer(AccessTokenIssuer):
    """Подписывает короткоживущие JWT (HS256).

    В токене только идентификаторы: ни телефона, ни прочих персональных данных —
    payload JWT читается любым, у кого есть токен.
    """

    ALGORITHM = "HS256"

    def __init__(self, secret: str, issuer: str, ttl: timedelta, id_generator: IdGenerator) -> None:
        """Задать ключ, издателя и срок жизни."""
        self._secret = secret
        self._issuer = issuer
        self._ttl = ttl
        self._id_generator = id_generator

    def issue(self, account_id: UUID, session_id: UUID, now: datetime) -> AccessToken:
        """Выпустить токен клиента."""
        expires_at = now + self._ttl
        claims = {
            "iss": self._issuer,
            "sub": str(account_id),
            "sid": str(session_id),
            "kind": "client",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(self._id_generator.new()),
        }
        return AccessToken(jwt.encode(claims, self._secret, algorithm=self.ALGORITHM), expires_at)


class JwtAccessTokenVerifier:
    """Проверяет подпись, издателя и срок access-токена.

    Срок проверяется по ``Clock`` приложения, а не по системным часам внутри
    PyJWT: так правило «токен истёк» детерминированно тестируется.
    """

    def __init__(
        self, secret: str, issuer: str, clock: Clock, leeway: timedelta = timedelta(seconds=10)
    ) -> None:
        """Задать ключ, издателя, часы и допуск на рассинхрон часов."""
        self._secret = secret
        self._issuer = issuer
        self._clock = clock
        self._leeway = leeway

    def verify(self, token: str) -> AccessClaims:
        """Вернуть утверждения или бросить ``InvalidSessionError``."""
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[JwtAccessTokenIssuer.ALGORITHM],
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "sid", "iss"], "verify_exp": False},
            )
            if self._clock.now() - self._leeway >= datetime.fromtimestamp(int(claims["exp"]), UTC):
                raise InvalidSessionError("Access-токен истёк")
            return AccessClaims(UUID(claims["sub"]), UUID(claims["sid"]), str(claims.get("kind", "")))
        except (jwt.PyJWTError, ValueError, KeyError) as error:
            raise InvalidSessionError() from error
