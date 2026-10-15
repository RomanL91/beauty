"""Общие фикстуры."""

from __future__ import annotations

import pytest

from tests.fakes import FrozenClock


@pytest.fixture
def clock() -> FrozenClock:
    """Управляемые часы."""
    return FrozenClock()
