"""CLI спайка: ``python -m spikes.hermes provision | mcp | run``."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable
from pathlib import Path

import httpx
import uvicorn

from spikes.hermes.client import HermesRunsClient
from spikes.hermes.mcp_stub import StubServerFactory
from spikes.hermes.provisioning import HermesProfileProvisioner, LocalCommandRunner, ProfileFiles
from spikes.hermes.registry import MasterRegistry
from spikes.hermes.report import SpikeReportWriter
from spikes.hermes.scenarios import SCENARIOS, SpikeContext
from spikes.hermes.tickets import TicketCodec


class SpikeSettings:
    """Настройки спайка из окружения."""

    def __init__(self) -> None:
        """Прочитать переменные ``SPIKE_*``."""
        self.data_dir = Path(os.environ.get("SPIKE_DATA_DIR", "./var/spike"))
        self.hermes_url = os.environ.get("SPIKE_HERMES_URL", "http://127.0.0.1:8642")
        self.hermes_cmd = os.environ.get("SPIKE_HERMES_CMD", "hermes")
        self.profiles_root = Path(
            os.environ.get("SPIKE_PROFILES_ROOT", str(Path.home() / ".hermes" / "profiles"))
        )
        self.ticket_secret = os.environ.get("SPIKE_TICKET_SECRET", "").encode()
        self.template = os.environ.get("SPIKE_TEMPLATE_PROFILE", "beauty-template")

    @property
    def registry(self) -> MasterRegistry:
        """Реестр мастеров спайка."""
        return MasterRegistry(self.data_dir / "masters.json")

    def provisioner(self) -> HermesProfileProvisioner:
        """Провижинер профилей."""
        return HermesProfileProvisioner(
            LocalCommandRunner.from_string(self.hermes_cmd),
            ProfileFiles(self.profiles_root),
            self.registry,
            self.template,
        )


class SpikeCli:
    """Подкоманды спайка."""

    def __init__(self, settings: SpikeSettings) -> None:
        """Получить настройки."""
        self._settings = settings

    async def provision(self, count: int) -> None:
        """Создать ``count`` профилей мастеров."""
        provisioner = self._settings.provisioner()
        for number in range(1, count + 1):
            record = await provisioner.provision(f"Мастер {number}")
            print(f"{record.profile}\t{record.display_name}")

    def mcp(self, host: str, port: int) -> None:
        """Поднять MCP-заглушку (streamable HTTP, путь /mcp)."""
        factory = StubServerFactory(
            self._settings.data_dir / "masters.json",
            self._settings.data_dir / "calls.jsonl",
            self._settings.ticket_secret,
        )
        uvicorn.run(factory.create().streamable_http_app(host=host), host=host, port=port)

    async def run(self, names: list[str]) -> None:
        """Прогнать сценарии и записать отчёт."""
        masters = self._settings.registry.load()
        if not masters:
            raise SystemExit("Нет профилей: сначала выполните provision")
        async with httpx.AsyncClient(timeout=60) as http:
            context = SpikeContext(
                client=HermesRunsClient(self._settings.hermes_url, http),
                masters=masters,
                tickets=TicketCodec(self._settings.ticket_secret),
                journal_path=self._settings.data_dir / "calls.jsonl",
                provisioner=self._settings.provisioner(),
            )
            reports = []
            for name in names:
                report = await SCENARIOS[name]().run(context)
                print(f"{'✅' if report.passed else '❌'} {name}: {report.metrics}")
                reports.append(report)
        print(SpikeReportWriter(self._settings.data_dir).write(reports))


def main() -> None:
    """Разбор аргументов и запуск."""
    parser = argparse.ArgumentParser(prog="python -m spikes.hermes")
    commands = parser.add_subparsers(dest="command", required=True)
    provision = commands.add_parser("provision", help="создать профили мастеров из шаблона")
    provision.add_argument("--count", type=int, default=5)
    mcp = commands.add_parser("mcp", help="поднять MCP-заглушку beauty-tools")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=8765)
    run = commands.add_parser("run", help="прогнать сценарии")
    run.add_argument("scenarios", nargs="*", default=list(SCENARIOS), choices=list(SCENARIOS))
    arguments = parser.parse_args()

    cli = SpikeCli(SpikeSettings())
    actions: dict[str, Callable[[], object]] = {
        "provision": lambda: asyncio.run(cli.provision(arguments.count)),
        "mcp": lambda: cli.mcp(arguments.host, arguments.port),
        "run": lambda: asyncio.run(cli.run(arguments.scenarios)),
    }
    actions[arguments.command]()


if __name__ == "__main__":
    main()
