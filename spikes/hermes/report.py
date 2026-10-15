"""Отчёт спайка в Markdown и JSON."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from spikes.hermes.scenarios import ScenarioReport


class SpikeReportWriter:
    """Пишет ``report.md`` (для человека) и ``report.json`` (сырые данные)."""

    def __init__(self, directory: Path) -> None:
        """Задать каталог отчёта."""
        self._directory = directory

    def write(self, reports: Sequence[ScenarioReport]) -> Path:
        """Сохранить отчёты и вернуть путь к Markdown."""
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / "report.json").write_text(
            json.dumps([asdict(report) for report in reports], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        lines = [
            f"# Спайк Hermes — {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
            "",
            "| Сценарий | Гипотеза | Итог |",
            "|---|---|---|",
        ]
        lines += [f"| {r.name} | {r.hypothesis} | {'✅' if r.passed else '❌'} |" for r in reports]
        for report in reports:
            lines += [
                "",
                f"## {report.name}",
                "",
                "```json",
                json.dumps(report.metrics, ensure_ascii=False, indent=2),
                "```",
            ]
            lines += [f"- {note}" for note in report.notes]
        path = self._directory / "report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
