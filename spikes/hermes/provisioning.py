"""Провижининг профилей Hermes под мастеров.

Профиль мастера клонируется из шаблона ``beauty-template``, который оператор
настраивает один раз: модель, ключ провайдера, ограничение тулсетов и подключение
MCP ``beauty`` с ``${BEAUTY_MCP_TOKEN}`` в заголовке. Клону остаётся только
получить собственные секреты в ``.env`` и SOUL.md с именем мастера.

Hermes при клонировании не копирует ``API_SERVER_KEY`` (это «канальный» секрет),
поэтому у каждого профиля свой ключ: под мультиплексором ``/p/<профиль>/``
принимает только ключ этого профиля.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import shlex
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

from spikes.hermes.registry import MasterRecord, MasterRegistry

_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")

SOUL_TEMPLATE = """# Администратор мастера {name}

Ты — администратор частного мастера по имени {name}. Ты ведёшь его дела так, как это
делал бы живой администратор салона: отвечаешь клиентам, записываешь, переносишь и
отменяешь визиты, напоминаешь, помнишь клиентов и их предпочтения.

## Правила
- Действуешь только через инструменты beauty. Ответить клиенту можно только
  инструментом send_message — обычный текст ответа клиент не увидит.
- В каждый вызов инструмента передавай тикет запуска из инструкций без изменений.
- Консультируя по процедурам, всегда указывай, что это ответ ИИ, и давай источники.
- Не раскрывай данные других клиентов. Не выдумывай свободное время — спрашивай
  find_free_slots.
- Если не уверен — честно скажи и предложи передать вопрос мастеру.
- Пиши кратко, тепло и по делу, на языке собеседника.
"""


class CommandRunner(ABC):
    """Исполнитель команд Hermes CLI (локально или в контейнере)."""

    @abstractmethod
    async def run(self, *arguments: str) -> str:
        """Выполнить команду и вернуть stdout; ненулевой код — исключение."""


class LocalCommandRunner(CommandRunner):
    """Команды на этой машине: ``hermes …``."""

    def __init__(self, prefix: Sequence[str]) -> None:
        """Префикс команды, например ``["hermes"]`` или ``["docker", "exec", "beauty-hermes", "hermes"]``."""
        self._prefix = tuple(prefix)

    @classmethod
    def from_string(cls, command: str) -> LocalCommandRunner:
        """Разобрать префикс из строки."""
        return cls(shlex.split(command))

    async def run(self, *arguments: str) -> str:
        """Запустить процесс без shell (аргументы не интерпретируются оболочкой)."""
        process = await asyncio.create_subprocess_exec(
            *self._prefix,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"{' '.join(arguments)}: {stderr.decode(errors='replace').strip()}")
        return stdout.decode(errors="replace")


class ProfileFiles:
    """Файлы профилей на диске хоста (каталог ``profiles`` из HERMES_HOME, смонтированный в контейнер)."""

    def __init__(self, profiles_root: Path) -> None:
        """Задать корень профилей."""
        self._root = profiles_root

    def upsert_env(self, profile: str, values: Mapping[str, str]) -> None:
        """Заменить или добавить переменные в ``.env`` профиля."""
        path = self._root / profile / ".env"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        pending = dict(values)
        result: list[str] = []
        for line in lines:
            match = _ENV_LINE.match(line)
            if match and match.group(1) in pending:
                result.append(f"{match.group(1)}={pending.pop(match.group(1))}")
            else:
                result.append(line)
        result.extend(f"{key}={value}" for key, value in pending.items())
        path.write_text("\n".join(result) + "\n", encoding="utf-8")
        path.chmod(0o600)

    def write_soul(self, profile: str, content: str) -> None:
        """Записать SOUL.md профиля."""
        (self._root / profile / "SOUL.md").write_text(content, encoding="utf-8")


class HermesProfileProvisioner:
    """Создаёт профиль мастера и регистрирует его в реестре спайка."""

    def __init__(
        self,
        runner: CommandRunner,
        files: ProfileFiles,
        registry: MasterRegistry,
        template_profile: str = "beauty-template",
    ) -> None:
        """Получить зависимости."""
        self._runner = runner
        self._files = files
        self._registry = registry
        self._template = template_profile

    async def provision(self, display_name: str) -> MasterRecord:
        """Склонировать шаблон, выдать секреты, записать SOUL.md."""
        master_id = uuid4().hex
        record = MasterRecord(
            master_id=master_id,
            display_name=display_name,
            profile=f"m-{master_id[:12]}",
            api_server_key=secrets.token_urlsafe(32),
            mcp_token=secrets.token_urlsafe(32),
        )
        await self._runner.run("profile", "create", record.profile, "--clone-from", self._template)
        self._files.upsert_env(
            record.profile,
            {"API_SERVER_KEY": record.api_server_key, "BEAUTY_MCP_TOKEN": record.mcp_token},
        )
        self._files.write_soul(record.profile, SOUL_TEMPLATE.format(name=display_name))
        self._registry.add(record)
        return record
