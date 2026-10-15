"""Тесты кита спайка Hermes: тикеты, реестр, правка .env профиля, провижинер."""

from __future__ import annotations

from pathlib import Path

import pytest

from spikes.hermes.provisioning import CommandRunner, HermesProfileProvisioner, ProfileFiles
from spikes.hermes.registry import MasterRegistry
from spikes.hermes.tickets import AgentFace, InvalidTicketError, TicketCodec

SECRET = b"s" * 48


class TestTicketCodec:
    """Capability-тикеты."""

    def test_roundtrip(self) -> None:
        """Выпущенный тикет проверяется и несёт права."""
        codec = TicketCodec(SECRET)
        ticket = codec.verify(codec.issue("m1", AgentFace.FRONT_DESK, "conv", "card", now=1000), now=1001)
        assert (ticket.master_id, ticket.face, ticket.client_card_id) == ("m1", AgentFace.FRONT_DESK, "card")

    def test_tampering_and_expiry(self) -> None:
        """Подмена тела, чужой ключ и истечение — отказ."""
        codec = TicketCodec(SECRET, ttl_seconds=10)
        token = codec.issue("m1", AgentFace.BACK_OFFICE, "office", now=1000)
        body, signature = token.split(".")
        forged_body = (
            TicketCodec(b"x" * 48).issue("m2", AgentFace.BACK_OFFICE, "office", now=1000).split(".")[0]
        )
        with pytest.raises(InvalidTicketError):
            codec.verify(f"{forged_body}.{signature}", now=1001)
        with pytest.raises(InvalidTicketError):
            TicketCodec(b"x" * 48).verify(token, now=1001)
        with pytest.raises(InvalidTicketError):
            codec.verify(token, now=1010)
        with pytest.raises(InvalidTicketError):
            codec.verify("garbage", now=1001)
        assert body

    def test_short_secret_rejected(self) -> None:
        """Слабый ключ — ошибка конфигурации."""
        with pytest.raises(ValueError, match="32"):
            TicketCodec(b"short")


class FakeRunner(CommandRunner):
    """Вместо Hermes CLI создаёт каталог профиля, как это сделал бы ``profile create``."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, ...]] = []

    async def run(self, *arguments: str) -> str:
        self.calls.append(arguments)
        profile = self.root / arguments[2]
        profile.mkdir(parents=True)
        (profile / ".env").write_text("OPENROUTER_API_KEY=keep-me\nAPI_SERVER_KEY=template-key\n")
        return ""


async def test_provisioner_clones_template_and_writes_secrets(tmp_path: Path) -> None:
    """Профиль клонируется из шаблона, получает свои секреты и SOUL.md, попадает в реестр."""
    runner = FakeRunner(tmp_path)
    registry = MasterRegistry(tmp_path / "masters.json")
    record = await HermesProfileProvisioner(runner, ProfileFiles(tmp_path), registry).provision("Алиса")

    assert runner.calls == [("profile", "create", record.profile, "--clone-from", "beauty-template")]
    env = (tmp_path / record.profile / ".env").read_text()
    assert "OPENROUTER_API_KEY=keep-me" in env
    assert f"API_SERVER_KEY={record.api_server_key}" in env
    assert "template-key" not in env
    assert f"BEAUTY_MCP_TOKEN={record.mcp_token}" in env
    assert "Алиса" in (tmp_path / record.profile / "SOUL.md").read_text()
    assert registry.by_mcp_token()[record.mcp_token].profile == record.profile
