"""Тесты строительных блоков домена."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from beauty.shared.domain.aggregate import AggregateRoot
from beauty.shared.domain.events import DomainEvent
from beauty.shared.domain.ids import UuidV7Generator
from beauty.shared.domain.secrets import HashedSecret
from beauty.shared.domain.specification import Specification
from beauty.shared.infrastructure.db.tracker import AggregateTracker


class TestUuidV7:
    """Генератор UUIDv7."""

    def test_version_and_variant(self) -> None:
        """Версия 7 и вариант RFC 4122."""
        value = UuidV7Generator().new()
        assert value.version == 7
        assert value.variant == "specified in RFC 4122"

    def test_strictly_increasing_within_burst(self) -> None:
        """Тысяча id подряд строго возрастают (монотонность внутри миллисекунды)."""
        generator = UuidV7Generator()
        values = [generator.new() for _ in range(10_000)]
        assert values == sorted(values)
        assert len(set(values)) == len(values)

    def test_timestamp_prefix_matches_clock(self) -> None:
        """Старшие 48 бит — миллисекунды Unix-времени."""
        before = int(datetime.now(UTC).timestamp() * 1000)
        value = UuidV7Generator().new()
        assert abs((value.int >> 80) - before) < 5_000


@dataclass(frozen=True, kw_only=True)
class _Happened(DomainEvent):
    routing_key = "test.thing.happened"
    number: int


class _Thing(AggregateRoot):
    def __init__(self, number: int) -> None:
        self.id = UuidV7Generator().new()
        self.number = number

    def poke(self, now: datetime) -> None:
        self._record(_Happened(occurred_at=now, number=self.number))


class TestAggregateEvents:
    """Сбор событий агрегатов."""

    def test_pull_clears_buffer(self) -> None:
        """События забираются один раз."""
        thing = _Thing(1)
        thing.poke(datetime.now(UTC))
        assert len(thing.pull_events()) == 1
        assert thing.pull_events() == []

    def test_lazy_buffer_without_init(self) -> None:
        """Буфер есть даже у объекта, созданного в обход ``__init__`` (как это делает ORM)."""
        thing = _Thing.__new__(_Thing)
        thing.number = 7
        thing.id = UuidV7Generator().new()
        thing.poke(datetime.now(UTC))
        assert thing.has_pending_events

    def test_tracker_preserves_order_and_deduplicates(self) -> None:
        """Трекер собирает события в порядке появления агрегатов, без дублей агрегатов."""
        now = datetime.now(UTC)
        first, second = _Thing(1), _Thing(2)
        tracker = AggregateTracker()
        tracker.track(first)
        tracker.track(second)
        tracker.track(first)
        first.poke(now)
        second.poke(now)
        first.poke(now)
        numbers = [event.number for event in tracker.collect_events()]  # type: ignore[attr-defined]
        assert numbers == [1, 1, 2]


class TestHashedSecret:
    """Хеш секрета."""

    def test_matches_only_same_secret(self) -> None:
        """Совпадает только исходный секрет; сам секрет не хранится."""
        hashed = HashedSecret.of("s3cr3t")
        assert hashed.matches("s3cr3t")
        assert not hashed.matches("s3cr3T")
        assert "s3cr3t" not in hashed.digest


class _Even(Specification[int]):
    def is_satisfied_by(self, candidate: int) -> bool:
        return candidate % 2 == 0


class _Positive(Specification[int]):
    def is_satisfied_by(self, candidate: int) -> bool:
        return candidate > 0


class TestSpecification:
    """Композиция спецификаций."""

    def test_combinators(self) -> None:
        """И, ИЛИ, НЕ."""
        even, positive = _Even(), _Positive()
        assert (even & positive).is_satisfied_by(4)
        assert not (even & positive).is_satisfied_by(-4)
        assert (even | positive).is_satisfied_by(3)
        assert (~even).is_satisfied_by(3)
