"""Политика cookie авторизации.

* ``bk_auth_challenge`` — секрет браузера, начавшего вход; виден только путям входа;
* ``bk_refresh`` — refresh-токен; виден только путям сессии.

Оба — ``HttpOnly`` (недоступны JS: XSS не украдёт), ``Secure`` и ``SameSite=Strict``.
PWA мастеров живут на поддоменах ``*.beautiful.kz`` — это один «сайт» (eTLD+1),
поэтому ``SameSite=Strict`` не мешает запросам PWA к API, но отсекает чужие сайты.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Response

CHALLENGE_COOKIE = "bk_auth_challenge"
REFRESH_COOKIE = "bk_refresh"


class AuthCookiePolicy:
    """Устанавливает и очищает cookie авторизации."""

    def __init__(
        self,
        api_prefix: str,
        challenge_ttl: timedelta,
        secure: bool = True,
        domain: str | None = None,
    ) -> None:
        """Задать префикс API, срок cookie входа и флаги."""
        self._challenge_path = f"{api_prefix}/auth/telegram"
        self._session_path = f"{api_prefix}/auth/session"
        self._challenge_ttl = challenge_ttl
        self._secure = secure
        self._domain = domain

    def set_challenge(self, response: Response, browser_secret: str) -> None:
        """Сохранить секрет браузера на время входа."""
        response.set_cookie(
            CHALLENGE_COOKIE,
            browser_secret,
            max_age=int(self._challenge_ttl.total_seconds()),
            path=self._challenge_path,
            domain=self._domain,
            secure=self._secure,
            httponly=True,
            samesite="strict",
        )

    def clear_challenge(self, response: Response) -> None:
        """Удалить секрет входа после обмена."""
        response.delete_cookie(
            CHALLENGE_COOKIE,
            path=self._challenge_path,
            domain=self._domain,
            secure=self._secure,
            httponly=True,
        )

    def set_refresh(
        self, response: Response, refresh_token: str, expires_at: datetime, now: datetime
    ) -> None:
        """Сохранить refresh-токен."""
        response.set_cookie(
            REFRESH_COOKIE,
            refresh_token,
            max_age=max(int((expires_at - now).total_seconds()), 0),
            path=self._session_path,
            domain=self._domain,
            secure=self._secure,
            httponly=True,
            samesite="strict",
        )

    def clear_refresh(self, response: Response) -> None:
        """Удалить refresh-токен."""
        response.delete_cookie(
            REFRESH_COOKIE, path=self._session_path, domain=self._domain, secure=self._secure, httponly=True
        )
