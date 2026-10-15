"""CLI спайка: ``python -m spikes.hermes bootstrap | provision | mcp | run``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Callable
from pathlib import Path

import httpx
import uvicorn

from spikes.hermes.bootstrap import HermesHealthWaiter, SpikeBootstrap, TemplateProfileBootstrapper
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
        self.model = os.environ.get("SPIKE_MODEL", "google/gemini-2.5-flash")
        self.masters = int(os.environ.get("SPIKE_MASTERS", "5"))
        self.mcp_url = os.environ.get("SPIKE_MCP_URL", "http://mcp:8765/mcp")
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        owner = os.environ.get("SPIKE_PROFILES_OWNER", "")
        self.profiles_owner = tuple(int(part) for part in owner.split(":")) if owner else None

    @property
    def registry(self) -> MasterRegistry:
        """Реестр мастеров спайка."""
        return MasterRegistry(self.data_dir / "masters.json")

    def runner(self) -> LocalCommandRunner:
        """Исполнитель команд Hermes CLI."""
        return LocalCommandRunner.from_string(self.hermes_cmd)

    def files(self) -> ProfileFiles:
        """Доступ к файлам профилей."""
        owner = self.profiles_owner
        return ProfileFiles(self.profiles_root, (owner[0], owner[1]) if owner else None)

    def provisioner(self) -> HermesProfileProvisioner:
        """Провижинер профилей."""
        return HermesProfileProvisioner(self.runner(), self.files(), self.registry, self.template)

    def bootstrap(self) -> SpikeBootstrap:
        """Первичная настройка экземпляра Hermes."""
        if not self.openrouter_key:
            raise SystemExit("Не задан OPENROUTER_API_KEY")
        if len(self.ticket_secret) < 32:
            raise SystemExit("SPIKE_TICKET_SECRET должен быть не короче 32 символов")
        template = TemplateProfileBootstrapper(
            self.runner(),
            self.files(),
            Path(__file__).parent / "templates" / "beauty-template.config.yaml",
            self.model,
            {"OPENROUTER_API_KEY": self.openrouter_key, "BEAUTY_MCP_URL": self.mcp_url},
            self.template,
        )
        return SpikeBootstrap(
            HermesHealthWaiter(self.hermes_url), template, self.provisioner(), self.registry, self.masters
        )


class SpikeCli:
    """Подкоманды спайка."""

    def __init__(self, settings: SpikeSettings) -> None:
        """Получить настройки."""
        self._settings = settings

    async def bootstrap(self) -> None:
        """Настроить шаблон и дозавести мастеров."""
        await self._settings.bootstrap().run()

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
    commands.add_parser("bootstrap", help="настроить шаблон и создать мастеров (идемпотентно)")
    provision = commands.add_parser("provision", help="создать профили мастеров из шаблона")
    provision.add_argument("--count", type=int, default=5)
    mcp = commands.add_parser("mcp", help="поднять MCP-заглушку beauty-tools")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=8765)
    run = commands.add_parser("run", help="прогнать сценарии")
    # Без default: Python 3.13 сверяет default целиком с choices, и `run` без аргументов падает.
    run.add_argument("scenarios", nargs="*", choices=list(SCENARIOS))
    arguments = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cli = SpikeCli(SpikeSettings())
    actions: dict[str, Callable[[], object]] = {
        "bootstrap": lambda: asyncio.run(cli.bootstrap()),
        "provision": lambda: asyncio.run(cli.provision(arguments.count)),
        "mcp": lambda: cli.mcp(arguments.host, arguments.port),
        "run": lambda: asyncio.run(cli.run(arguments.scenarios or list(SCENARIOS))),
    }
    actions[arguments.command]()


if __name__ == "__main__":
    main()
