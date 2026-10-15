# Спайк: Hermes как «мозг» администратора мастера

Цель — до начала контекста `agent` проверить на живом Hermes гипотезы, от которых
зависит архитектура. Кит самодостаточен: провижинер профилей, MCP-заглушка
`beauty-tools` с тикетами и журналом вызовов, сценарии и отчёт.

> Запускайте на **отдельном экземпляре Hermes** (свой контейнер), не на
> `voltera-agent`: мультиплексор обслуживает все профили одного `HERMES_HOME`, и
> `max_concurrent_runs` у них общий — спайк смешается с офисом VOLTERA.

## Гипотезы и критерии

| # | Сценарий | Гипотеза | Успех |
|---|---|---|---|
| H1 | `concurrency` | Мультиплексор держит параллельные диалоги N мастеров | 0 ответов 429/ошибок; записать p50/p95 |
| H2 | `same_session` | Ходы одной `session_id` сериализуются Hermes | Вторая латентность ≈ первая + ход; иначе нужна наша сериализация |
| H3 | `isolation` | Prompt injection на ресепшне не даёт чужих данных | 0 вызовов с чужим мастером/ролью, 0 утечек телефонов в `send_message` |
| H4 | `learning` | Факт, сказанный мастером, живёт между сессиями | Ответ во 2-й сессии содержит оба факта |
| H5 | `hot_profile` | Новый мастер обслуживается без рестарта gateway | `/p/<профиль>/v1/models` → 200 за ≤ 30 с |

Плюс вручную (по журналу и логам Hermes):

* **Память на мастера** — `~/.hermes/profiles/m-*/memories/MEMORY.md` растёт у
  «своего» профиля и не трогает соседей.
* **Ресурсы** — RSS процесса gateway при 5 / 20 / 50 профилях (`ps -o rss`).
* **Стоимость** — токены на ход (`usage` в `GET /v1/runs/{id}`).

## Быстрый старт в Docker (рекомендуется)

Всё поднимается одной командой: отдельный Hermes, MCP-заглушка и bootstrap.
Bootstrap создаёт профиль-шаблон с моделью OpenRouter и ограничением тулсетов,
а затем профили мастеров. Руками нужно вписать только ключ OpenRouter.

```bash
cd spikes/hermes/docker
cp .env.example .env
# впишите OPENROUTER_API_KEY, затем сгенерируйте два секрета:
sed -i "s/^HERMES_DEFAULT_API_KEY=.*/HERMES_DEFAULT_API_KEY=$(openssl rand -hex 32)/" .env
sed -i "s/^SPIKE_TICKET_SECRET=.*/SPIKE_TICKET_SECRET=$(openssl rand -hex 32)/" .env

docker compose up -d --build
docker compose logs -f bootstrap        # ждём «Готово: профилей мастеров — 5»
docker compose run --rm spike run       # все сценарии; отчёт — ./out/report.md
```

Полезное:

* `docker compose run --rm spike run isolation learning` — выборочные сценарии;
* `docker exec beauty-hermes hermes profile list` — профили в контейнере;
* `docker compose logs -f hermes` — логи gateway;
* `./out/calls.jsonl` — журнал всех вызовов MCP-инструментов агентами;
* полный сброс: `docker compose down -v && rm -rf out`.

Bootstrap идемпотентен: после смены `SPIKE_MODEL` или `SPIKE_MASTERS` выполните
`docker compose run --rm bootstrap`.

## Подготовка без Docker

```bash
pip install -e '.[spike]'
export SPIKE_DATA_DIR=./var/spike
export SPIKE_TICKET_SECRET=$(python -c 'import secrets;print(secrets.token_urlsafe(48))')
export SPIKE_HERMES_URL=http://127.0.0.1:8642           # общий listener мультиплексора
export SPIKE_HERMES_CMD="docker exec beauty-hermes hermes"  # или просто "hermes"
export SPIKE_PROFILES_ROOT=/srv/beauty-hermes/data/profiles  # profiles/ из HERMES_HOME на хосте
```

1. **Шаблон.** `hermes profile create beauty-template`, затем
   `hermes -p beauty-template setup` (модель через OpenRouter). Допишите в его
   `config.yaml` блок из `templates/beauty-template.config.yaml`, а в `.env` —
   `BEAUTY_MCP_URL=http://<хост-заглушки>:8765/mcp`.
2. **Default-профиль** экземпляра должен иметь `API_SERVER_ENABLED=true` и свой
   `API_SERVER_KEY` — его listener и есть мультиплексор (`/p/<профиль>/…`).
3. **Заглушка MCP:** `python -m spikes.hermes mcp --host 0.0.0.0 --port 8765`
   (должна быть доступна из контейнера Hermes).
4. **Мастера:** `python -m spikes.hermes provision --count 5`.
5. **Сценарии:** `python -m spikes.hermes run` (или выборочно:
   `python -m spikes.hermes run isolation learning`).

Отчёт — `var/spike/report.md`, журнал MCP — `var/spike/calls.jsonl`.

## Что проверить в первую очередь (неясно из документации)

* `platform_toolsets.api_server` и `agent.disabled_toolsets` действительно убирают
  `terminal`/`file` у запусков через Runs API: в первом же ответе
  `GET /p/<профиль>/v1/toolsets` не должно быть этих тулсетов.
* `${BEAUTY_MCP_TOKEN}` в `headers` резолвится из `.env` клона, а не шаблона —
  проверяется журналом заглушки (у каждого профиля свой `master_id`).
* `max_concurrent_runs` — общий на listener или на профиль. Прогоните H1 с
  `--count 20` и `gateway.api_server.max_concurrent_runs: 10`: если 429 при
  20 параллельных диалогах — лимит общий, планируем пул экземпляров.

## Как решение повлияет на архитектуру

* H1/H5 не прошли → адаптер `AgentRuntime` получает **пул экземпляров Hermes**
  с шардированием мастеров (consistent hashing по `master_id`).
* H2 не прошёл → сериализация ходов диалога только на нашей стороне (у нас она и
  так есть: consistent-hash exchange + single active consumer).
* H3 не прошёл → заглушка покажет, через какой инструмент ушли данные; ужесточаем
  MCP (агенту ресепшна — только `send_message`, `find_free_slots`, `book_appointment`).
* H4 не прошёл → память мастера держим в своей БД и отдаём агенту инструментом
  `get_master_notes` (memory provider plugin Hermes — альтернатива).
