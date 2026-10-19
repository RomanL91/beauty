"""Админ-панель: пароли, перебор, сессии."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from beauty.contexts.admin.domain.admin import LOCK_FOR, MAX_FAILURES, Administrator
from beauty.contexts.admin.domain.errors import InvalidAdminLogin, WeakPassword
from beauty.contexts.admin.domain.passwords import DUMMY_HASH, hash_password, verify_password
from beauty.contexts.admin.domain.session import AdminSession

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def test_password_hash_and_verify() -> None:
    """scrypt с солью: разные хеши одного пароля; неверный, испорченный и пустой — нет."""
    first, second = hash_password("correct horse"), hash_password("correct horse")
    assert first != second
    assert first.startswith("scrypt$16384$8$1$")
    assert verify_password("correct horse", first)
    assert not verify_password("correct horsE", first)
    assert not verify_password("correct horse", "md5$abc")
    assert not verify_password("correct horse", first.replace("scrypt", "bcrypt"))
    assert not verify_password("anything", DUMMY_HASH)
    with pytest.raises(WeakPassword):
        hash_password("short")
    with pytest.raises(WeakPassword):
        hash_password(" " * 12)


def admin() -> Administrator:
    """Администратор."""
    return Administrator.register(
        admin_id=uuid4(), login="  Owner.Main ", display_name=" Хозяин  сервиса ", password_hash="h", now=NOW
    )


def test_login_and_name_are_normalized() -> None:
    """Логин — без регистра и пробелов; имя — без лишних пробелов; кириллица в логине — нет."""
    created = admin()
    assert (created.login, created.display_name, created.active) == ("owner.main", "Хозяин сервиса", True)
    with pytest.raises(InvalidAdminLogin):
        Administrator.register(admin_id=uuid4(), login="хозяин", display_name="Х", password_hash="h", now=NOW)


def test_brute_force_lock() -> None:
    """5 неверных паролей подряд — вход закрыт на 15 минут; успешный вход сбрасывает счётчик."""
    target = admin()
    for _ in range(MAX_FAILURES - 1):
        target.login_failed(NOW)
    assert not target.locked(NOW)
    target.logged_in(NOW)
    for _ in range(MAX_FAILURES):
        target.login_failed(NOW)
    assert target.locked(NOW)
    assert target.locked(NOW + LOCK_FOR - timedelta(seconds=1))
    assert not target.locked(NOW + LOCK_FOR)


def test_session_validity() -> None:
    """Секрет из cookie, срок, отзыв."""
    session = AdminSession.open(
        session_id=uuid4(),
        admin_id=uuid4(),
        secret="s3cret",
        csrf_token="c",
        now=NOW,
        ttl=timedelta(hours=12),
    )
    assert session.valid("s3cret", NOW)
    assert not session.valid("other", NOW)
    assert not session.valid("s3cret", NOW + timedelta(hours=12))
    session.revoke(NOW)
    assert not session.valid("s3cret", NOW)
