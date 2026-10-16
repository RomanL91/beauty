"""Адаптеры Hermes: Runs API (на подменённом HTTP) и профили (на временном каталоге)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import yaml

from beauty.contexts.agent.application.ports import RunRequest
from beauty.contexts.agent.infrastructure.hermes import CommandRunner, HermesTemplate, ProfileFiles
from beauty.contexts.agent.infrastructure.runtime import HermesRuntime

REQUEST = RunRequest(
    profile_name="m-alisa",
    api_key="runs-key",
    session_id="conv-1",
    input="Привет",
    instructions="Тикет хода: t-abcdefgh",
    idempotency_key="msg-1",
)


def hermes(*polls: dict[str, Any], created: int = 202) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """HTTP-клиент, который отвечает как мультиплексор Hermes."""
    seen: list[httpx.Request] = []
    pending = list(polls)

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/stop"):
            return httpx.Response(200, json={"status": "stopping"})
        if request.method == "POST":
            return httpx.Response(created, json={"run_id": "run-1", "status": "queued"})
        return httpx.Response(200, json=pending.pop(0) if len(pending) > 1 else pending[0])

    return httpx.AsyncClient(transport=httpx.MockTransport(handle)), seen


async def test_run_polls_until_terminal_status() -> None:
    """Ход: POST с ключом профиля и Idempotency-Key, опрос до терминального статуса."""
    http, seen = hermes({"status": "running"}, {"status": "completed", "output": "Здравствуйте!"})
    outcome = await HermesRuntime("http://hermes:8642/", http, poll_interval=0).run(REQUEST)
    assert (outcome.status, outcome.output, outcome.ok) == ("completed", "Здравствуйте!", True)
    started = seen[0]
    assert str(started.url) == "http://hermes:8642/p/m-alisa/v1/runs"
    assert started.headers["Authorization"] == "Bearer runs-key"
    assert started.headers["Idempotency-Key"] == "msg-1"
    assert json.loads(started.content) == {
        "input": "Привет",
        "session_id": "conv-1",
        "instructions": "Тикет хода: t-abcdefgh",
    }
    assert str(seen[-1].url) == "http://hermes:8642/p/m-alisa/v1/runs/run-1"


async def test_service_notice_is_not_a_reply() -> None:
    """«⚠️ No reply: …» при статусе completed — не ответ клиенту, а неудачный ход."""
    notice = "⚠️ No reply: model didn't produce a reply this time, even after retries."
    http, _ = hermes({"status": "completed", "output": notice})
    outcome = await HermesRuntime("http://hermes:8642", http, poll_interval=0).run(REQUEST)
    assert (outcome.status, outcome.ok) == ("no_reply", False)


async def test_failures_are_outcomes() -> None:
    """Отказ, таймаут и недоступность — статусы, а не исключения."""
    rejected, _ = hermes({"status": "completed"}, created=401)
    assert (await HermesRuntime("http://h", rejected).run(REQUEST)).status == "http_401"

    slow, seen = hermes({"status": "running"})
    assert (await HermesRuntime("http://h", slow, poll_interval=0, timeout=0.01).run(REQUEST)).status == (
        "timeout"
    )
    assert (seen[-1].method, str(seen[-1].url)) == ("POST", "http://h/p/m-alisa/v1/runs/run-1/stop")

    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    down = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    assert (await HermesRuntime("http://h", down).run(REQUEST)).status == "unreachable"


class RecordingRunner(CommandRunner):
    """Вместо Hermes CLI создаёт каталог профиля."""

    def __init__(self, root: Path) -> None:
        super().__init__(["hermes"])
        self.root = root
        self.calls: list[tuple[str, ...]] = []

    async def run(self, *arguments: str) -> str:
        self.calls.append(arguments)
        if arguments[:2] == ("profile", "create"):
            (self.root / arguments[2]).mkdir()
        return ""


async def test_template_and_existing_profiles_follow_settings(tmp_path: Path) -> None:
    """Шаблон получает модель, тулсеты и MCP; профили мастеров — то же, их секреты целы."""
    files = ProfileFiles(tmp_path)
    runner = RecordingRunner(tmp_path)
    (tmp_path / "m-alisa").mkdir()
    (tmp_path / "m-alisa" / ".env").write_text("API_SERVER_KEY=secret\nBEAUTY_MCP_TOKEN=token\n")
    (tmp_path / "m-alisa" / "config.yaml").write_text("model:\n  default: old\nmemory:\n  enabled: true\n")
    (tmp_path / "default").mkdir()

    template = HermesTemplate(
        runner, files, {"provider": "custom", "default": "fake"}, {"BEAUTY_MCP_URL": "http://mcp:8765/mcp"}
    )
    await template.ensure()
    assert files.profiles("m-") == ["m-alisa"]
    template.sync(files.profiles("m-"))

    assert runner.calls[0] == ("profile", "create", "beauty-template")
    assert ("-p", "beauty-template", "gateway", "stop") in runner.calls
    for profile in ("beauty-template", "m-alisa"):
        config = yaml.safe_load((tmp_path / profile / "config.yaml").read_text())
        assert config["model"] == {"provider": "custom", "default": "fake"}
        assert config["tools"]["tool_search"]["enabled"] == "off"
        assert "terminal" in config["agent"]["disabled_toolsets"]
        assert config["mcp_servers"]["beauty"]["headers"]["Authorization"] == "Bearer ${BEAUTY_MCP_TOKEN}"
    alisa = tmp_path / "m-alisa"
    assert yaml.safe_load((alisa / "config.yaml").read_text())["memory"] == {"enabled": True}
    assert (alisa / ".env").read_text().splitlines() == [
        "API_SERVER_KEY=secret",
        "BEAUTY_MCP_TOKEN=token",
        "BEAUTY_MCP_URL=http://mcp:8765/mcp",
    ]
