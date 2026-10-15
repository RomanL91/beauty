"""Реестр мастеров спайка: профиль Hermes ↔ мастер ↔ секреты.

В продукте это таблица контекста Agent; в спайке — JSON-файл, который пишет
провижинер и читают MCP-заглушка и харнесс.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MasterRecord:
    """Мастер и его профиль Hermes."""

    master_id: str
    display_name: str
    profile: str
    api_server_key: str
    mcp_token: str


class MasterRegistry:
    """Хранилище записей в JSON-файле."""

    def __init__(self, path: Path) -> None:
        """Задать путь к файлу."""
        self._path = path

    def load(self) -> list[MasterRecord]:
        """Все записи (пустой список, если файла нет)."""
        if not self._path.exists():
            return []
        return [MasterRecord(**item) for item in json.loads(self._path.read_text(encoding="utf-8"))]

    def save(self, records: list[MasterRecord]) -> None:
        """Перезаписать файл."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(record) for record in records]
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, record: MasterRecord) -> None:
        """Добавить запись."""
        self.save([*self.load(), record])

    def by_mcp_token(self) -> dict[str, MasterRecord]:
        """Индекс по MCP-токену."""
        return {record.mcp_token: record for record in self.load()}
