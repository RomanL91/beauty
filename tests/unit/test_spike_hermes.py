"""Тесты кита спайка Hermes: тикеты, реестр, правка .env профиля, провижинер, сценарии."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import yaml

from spikes.hermes.bootstrap import SpikeBootstrap, TemplateProfileBootstrapper
from spikes.hermes.client import HermesRunsClient, RunResult
from spikes.hermes.provisioning import CommandRunner, HermesProfileProvisioner, ProfileFiles
from spikes.hermes.registry import MasterRecord, MasterRegistry
from spikes.hermes.scenarios import BaselineLatencyScenario, IsolationScenario, SpikeContext
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
        if arguments[:2] == ("profile", "create"):
            profile = self.root / arguments[2]
            profile.mkdir(parents=True)
            (profile / ".env").write_text("OPENROUTER_API_KEY=keep-me\nAPI_SERVER_KEY=template-key\n")
        return ""


async def test_provisioner_clones_template_and_writes_secrets(tmp_path: Path) -> None:
    """Профиль клонируется из шаблона, получает свои секреты и SOUL.md, попадает в реестр."""
    runner = FakeRunner(tmp_path)
    registry = MasterRegistry(tmp_path / "masters.json")
    record = await HermesProfileProvisioner(runner, ProfileFiles(tmp_path), registry).provision("Алиса")

    assert runner.calls == [
        ("profile", "create", record.profile, "--clone-from", "beauty-template"),
        ("-p", record.profile, "gateway", "restart"),
    ]
    env = (tmp_path / record.profile / ".env").read_text()
    assert "OPENROUTER_API_KEY=keep-me" in env
    assert f"API_SERVER_KEY={record.api_server_key}" in env
    assert "template-key" not in env
    assert f"BEAUTY_MCP_TOKEN={record.mcp_token}" in env
    assert "Алиса" in (tmp_path / record.profile / "SOUL.md").read_text()
    assert registry.by_mcp_token()[record.mcp_token].profile == record.profile


class TemplateRunner(CommandRunner):
    """Имитация Hermes CLI для bootstrap: создаёт каталоги профилей, остальное записывает."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, ...]] = []

    async def run(self, *arguments: str) -> str:
        self.calls.append(arguments)
        if arguments[:2] == ("profile", "create"):
            profile = self.root / arguments[2]
            profile.mkdir(parents=True)
            source = self.root / arguments[4] / ".env" if "--clone-from" in arguments else None
            env = source.read_text() if source and source.exists() else ""
            (profile / ".env").write_text(env)
            (profile / "config.yaml").write_text("display:\n  skin: default\nmodel:\n  temperature: 0.2\n")
        return ""


class ReadyWaiter:
    """Gateway «уже готов»."""

    async def wait(self) -> None:
        return None


async def test_bootstrap_is_idempotent_and_keys_reach_clones(tmp_path: Path) -> None:
    """Шаблон получает модель, MCP, тулсеты и ключи; клоны наследуют ключ; повтор не плодит мастеров."""
    runner = TemplateRunner(tmp_path)
    files = ProfileFiles(tmp_path)
    registry = MasterRegistry(tmp_path / "masters.json")
    overlay = Path(__file__).resolve().parents[2] / "spikes/hermes/templates/beauty-template.config.yaml"
    env = {"OPENROUTER_API_KEY": "sk-or-1", "BEAUTY_MCP_URL": "http://mcp:8765/mcp"}
    template = TemplateProfileBootstrapper(runner, files, overlay, "google/gemini-2.5-flash", env)
    bootstrap = SpikeBootstrap(
        ReadyWaiter(),  # type: ignore[arg-type]
        template,
        HermesProfileProvisioner(runner, files, registry),
        registry,
        masters=2,
    )
    await bootstrap.run()
    await bootstrap.run()

    config = yaml.safe_load((tmp_path / "beauty-template" / "config.yaml").read_text())
    assert config["model"] == {
        "temperature": 0.2,
        "provider": "openrouter",
        "default": "google/gemini-2.5-flash",
    }
    assert config["display"] == {"skin": "default"}
    assert "terminal" in config["agent"]["disabled_toolsets"]
    assert config["mcp_servers"]["beauty"]["headers"]["Authorization"] == "Bearer ${BEAUTY_MCP_TOKEN}"
    assert len(registry.load()) == 2
    for record in registry.load():
        assert "OPENROUTER_API_KEY=sk-or-1" in (tmp_path / record.profile / ".env").read_text()
    created = [call for call in runner.calls if call[:2] == ("profile", "create")]
    assert len(created) == 3, "шаблон и два мастера — каждый по одному разу"


MASTER = MasterRecord("m1", "Мастер 1", "m-1", "k" * 32, "t" * 32)


class ScriptedClient(HermesRunsClient):
    """Отдаёт заранее заданные ходы и пишет в журнал MCP заданные вызовы."""

    def __init__(
        self, journal: Path, latencies: list[float], calls: list[dict[str, object]], status: str = "completed"
    ) -> None:
        self._journal = journal
        self._latencies = iter(latencies)
        self._calls = calls
        self._status = status

    async def run(self, master: MasterRecord, text: str, session_id: str, instructions: str) -> RunResult:
        with self._journal.open("a", encoding="utf-8") as journal:
            for call in self._calls:
                journal.write(json.dumps({"ts": time.time(), **call}) + "\n")
        return RunResult(master.profile, session_id, self._status, "ok", next(self._latencies, 1.0), 200)


def _context(client: ScriptedClient, journal: Path) -> SpikeContext:
    return SpikeContext(client, [MASTER], TicketCodec(SECRET), journal)


@pytest.mark.parametrize(
    ("latencies", "status", "passed"),
    [
        ([5.0, 6.0, 12.0], "completed", True),
        ([5.0, 9.0, 12.0], "completed", False),
        ([1.0, 1.0, 1.0], "failed", False),
    ],
)
async def test_baseline_latency_judges_median_turn(
    tmp_path: Path, latencies: list[float], status: str, passed: bool
) -> None:
    journal = tmp_path / "calls.jsonl"
    report = await BaselineLatencyScenario().run(
        _context(ScriptedClient(journal, latencies, [], status), journal)
    )
    assert report.passed is passed


async def test_isolation_without_mcp_calls_is_not_a_pass(tmp_path: Path) -> None:
    journal = tmp_path / "calls.jsonl"
    report = await IsolationScenario().run(_context(ScriptedClient(journal, [], []), journal))
    assert report.passed is False
    assert report.metrics["mcp_calls"] == 0


async def test_isolation_passes_with_clean_mcp_calls(tmp_path: Path) -> None:
    journal = tmp_path / "calls.jsonl"
    call = {
        "tool": "send_message",
        "master_id": "m1",
        "face": AgentFace.FRONT_DESK.value,
        "arguments": {"text": "Нет"},
    }
    report = await IsolationScenario().run(_context(ScriptedClient(journal, [], [call]), journal))
    assert report.passed is True
