# Beauty — персональный ИИ-администратор мастера

Мастер-одиночка (массаж, ногти, брови, косметология) получает администратора, как
в салоне: тот ведёт переписку с клиентами, запись и график, помнит клиентов и
выполняет поручения мастера. Клиент приходит на страницу мастера
(`alisa-cosmetolog.beautiful.kz`, PWA) и общается в чате, а отвечает ему агент
мастера.

Этот репозиторий — первый вертикальный срез:

* **shared kernel** — фундамент всех контекстов;
* **контекст `identity`** — глобальный аккаунт клиента и вход через Telegram;
* **контекст `tenancy`** — мастер-арендатор, его публичная страница, услуги,
  расписание и свободные окна (`docs/tasks/backend-iteration-1-tenancy.md`);
* **контекст `booking`** — заявки и записи: удержание окна, подтверждение,
  автоотклонение, отмена и перенос, защита от двойной записи в БД;
* **контекст `conversations`** — переписка клиента с администратором мастера,
  поток SSE с досылкой по `Last-Event-ID`, администратор записи
  (`docs/tasks/backend-iteration-2-booking.md`);
* **кабинет мастера** — вход владельца страницы, график дня, решения по заявкам,
  чаты с клиентами и поток событий (`docs/tasks/backend-iteration-3-master-cabinet.md`);
* **контекст `agent`** — ИИ-администратор на Hermes + MCP: отвечает клиенту,
  консультирует по услугам, ищет окна, записывает и отменяет, передаёт диалог мастеру
  (`docs/tasks/backend-iteration-4-agent.md`), а в кабинете выполняет поручения мастера —
  график, заявки, отмены, выходные, сообщения клиентам, вопросы мастеру карточкой выбора
  (`docs/tasks/backend-iteration-5-assistant.md`);
* **контекст `notifications`** — push-уведомления (Web Push, VAPID) клиенту и мастеру и
  напоминание о визите (`docs/tasks/backend-iteration-6-push.md`);
* **спайк Hermes** (`spikes/hermes`) — проверка runtime агента до разработки
  контекста `agent`.

## Структура

```
src/beauty/
├── shared/                         # shared kernel
│   ├── domain/                     # AggregateRoot, DomainEvent, UUIDv7, Clock, Specification, HashedSecret
│   ├── application/                # CQRS: Command/Query/Handler, Mediator + middleware, UnitOfWork, FileStorage
│   └── infrastructure/
│       ├── db/                     # async engine, TransactionScope, SqlAlchemyUnitOfWork, VO-типы колонок
│       ├── outbox/                 # transactional outbox, relay, LISTEN/NOTIFY
│       ├── inbox/                  # идемпотентность консьюмеров
│       ├── messaging/              # RabbitMQ: топология, publisher confirms, консьюмер, retry/DLQ
│       ├── scheduling/             # отложенные задачи в Postgres (напоминания, таймауты)
│       ├── realtime/               # брокер → хаб процесса → SSE
│       ├── storage/                # локальное файловое хранилище (позже — S3)
│       └── web/                    # ошибки → HTTP, SSE-кадры
├── contexts/identity/
│   ├── domain/                     # AuthChallenge, ClientAccount, ClientSession, VO, события, спецификации
│   ├── application/                # команды, запросы, политики подтверждения, цепочка поиска аккаунта
│   ├── infrastructure/             # таблицы, маппинг, репозитории, JWT, read-модель, realtime-топики
│   ├── presentation/api|bot/       # FastAPI-контроллер + SSE, aiogram-бот
│   └── module.py                   # сборка контекста
├── contexts/tenancy/
│   ├── domain/                     # Master + Service, VO (slug, расписание, правила записи), SlotFinder
│   ├── application/                # команды кабинета/CLI, запросы страницы и окон, порты чтения
│   ├── infrastructure/             # таблицы (JSONB для расписания), маппинг, SQL-читатели
│   ├── presentation/api/           # GET /masters/{slug}, GET /masters/{slug}/slots
│   └── module.py
├── contexts/booking/               # Appointment, EXCLUDE USING gist, таймеры, /appointments
├── contexts/conversations/         # Conversation + Message, журнал ленты, SSE, администратор записи
├── contexts/notifications/         # подписки устройств, Web Push (RFC 8291/8292), кому и что сообщить
├── contexts/agent/                 # профили Hermes (ресепшн, кабинет), тикеты, ходы, лента поручений, MCP
├── bootstrap/                      # корень композиции (Pure DI), адаптеры между контекстами, демо-данные
└── entrypoints/                    # процессы: api, bot, relay, scheduler, worker, mcp; seed-demo, appointment, agent
migrations/                         # Alembic (async)
spikes/hermes/                      # кит спайка Hermes (см. его README)
devtools/fake_llm.py                # сценарная OpenAI-совместимая «модель» для прогона агента без ключа LLM
tests/unit | tests/integration      # 284 теста; интеграционные — на реальном PostgreSQL
```

## Вход клиента через Telegram

```
PWA                               API                          Бот
 │ POST /auth/telegram/challenges  │                             │
 │──────────────────────────────▶ │ challenge: nonce, код «42»  │
 │ ◀── deep link + код, cookie ── │ секрет браузера → httpOnly   │
 │ GET …/events (SSE)              │                             │
 │ пользователь открывает t.me/bot?start=<nonce> ──────────────▶ │ claim
 │                                 │                  [17][42][63]│ выбрать код с экрана
 │                                 │                   «Поделиться контактом»
 │                                 │ ◀── contact.user_id == from.id? ─ complete
 │ ◀── SSE: completed ───────────  │ (outbox → RabbitMQ → хаб API)
 │ POST …/session (cookie)         │ одноразовый обмен → access JWT + refresh-cookie
```

Две защиты сверх исходного флоу:

1. **Проверка `contact.user_id == from.id`.** Без неё пересланная карточка чужого
   контакта входит под чужим номером.
2. **Number matching (код на экране ↔ выбор в боте).** Без него возможен фишинг:
   злоумышленник начинает вход у себя и шлёт жертве свою deep link («запишитесь
   к мастеру»). Жертва делится контактом, и сессию получает браузер
   злоумышленника. Жертва не видит код на чужом экране, поэтому атака
   срывается. Цена — одно касание. Политику переключает
   `BEAUTY_AUTH__CONFIRMATION_POLICY` (`implicit` — только для локальной
   разработки).

Сессия устроена так:

* короткий access JWT;
* ротируемый refresh-токен в httpOnly-cookie, в БД хранится только хеш;
* повтор старого refresh после 30-секундного окна (окно — для двух вкладок PWA)
  считается кражей: сессия отзывается.

## Ключевые решения

| Решение | Почему |
|---|---|
| UUIDv7 генерируется в приложении | id нужен до сохранения (для событий); B-tree без случайных вставок; не требует PG 18 |
| Императивный маппинг, без `relationship` между агрегатами | Домен без SQLAlchemy; N+1 невозможен по построению |
| FK между агрегатами `DEFERRABLE INITIALLY DEFERRED` | Без связей ORM не знает порядок INSERT/UPDATE разных агрегатов; целостность проверяется при COMMIT |
| Оптимистичная блокировка (`version_id_col`) + `ConcurrencyRetryMiddleware` | Гонки (двойной клик, два устройства) решаются повтором команды, а не блокировками |
| Transactional outbox + relay (`SKIP LOCKED`, `LISTEN/NOTIFY`, publisher confirms) | Событие уходит тогда и только тогда, когда сохранены изменения; relay масштабируется |
| Inbox + `TransactionScope` (ContextVar, SAVEPOINT) | Отметка о доставке и эффект команды — одна транзакция; дочерние задачи к ней не присоединяются |
| Retry-очереди с TTL + DLQ | Экспоненциальная задержка без плагина delayed-message |
| Отложенные задачи в Postgres, а не в брокере | Напоминания нужно отменять и переносить вместе с записью |
| SSE: подписка на хаб **до** чтения статуса + периодическая перепроверка | Нет гонки «событие между чтением и подпиской»; поток переживает потерю события |
| `Clock` везде, включая проверку срока JWT | Правила времени тестируются детерминированно |

## Запуск

```bash
cp .env.example .env            # заполнить токен бота и JWT-секрет
docker compose up --build       # postgres, rabbitmq, migrate, seed, api, bot, relay, scheduler, worker, web
# API: http://localhost:8000/api/v1/docs
# PWA клиента: http://alisa.localhost:8080 · кабинет мастера: http://master.localhost:8080
```

Фронтенд (два PWA, контракт API, моки) — `frontend/README.md`.

Push-уведомления: `docker compose run --rm api push keys` печатает ключи VAPID — три строки
в `.env`, затем `docker compose up -d --build` (открытый ключ попадает в сборку PWA). Push
работает в безопасном контексте: https или `*.localhost`; по http через `nip.io` браузер
подписку не даст.

ИИ-администратор (профиль compose `agent`): Hermes, MCP-сервер `beauty-tools` и разовый
`agent-setup` — шаблоны профилей Hermes и профили демо-мастера alisa. У мастера два
профиля: ресепшн (`m-<id>`, клиенты, MCP `/mcp`) и кабинет (`m-<id>-office`, поручения
мастера, MCP `/office/mcp`) — агент ресепшна не видит инструментов мастера.

```bash
# в .env: BEAUTY_AGENT__RUNTIME=hermes, HERMES_DEFAULT_API_KEY=$(openssl rand -hex 32)
# и модель — OpenRouter (BEAUTY_AGENT__PROVIDER_API_KEY) или сценарная, см. .env.example
docker compose --profile agent up -d --build                     # + --profile fake-llm без ключа LLM
docker compose run --rm agent-setup "beauty agent provision <slug>"  # агент другому мастеру
docker compose run --rm agent-setup "beauty agent bootstrap"         # смена модели → шаблон и все профили
```

Расшифровка голосовых (клиентов и поручений мастера): `BEAUTY_SPEECH__PROVIDER=openrouter` —
тот же ключ OpenRouter, что у агента, модель `BEAUTY_SPEECH__MODEL` (по умолчанию
`openai/whisper-large-v3`); `fake` — сценарная фраза для стенда без ключа. Расшифровывает
worker в фоне; текст появляется под голосовым, агент отвечает по нему.

Ход: клиент пишет → `worker` (консьюмер `agent.front_desk`, single active consumer) →
Runs API Hermes (`/p/<профиль>/v1/runs`) → инструменты `beauty-tools` по MCP (токен профиля
+ короткий тикет хода) → ответ ИИ в чате. Не вышло (модель молчит, таймаут) — диалог
уходит мастеру с заметкой, клиенту лишнего не пишем.

Поручение: мастер пишет на экране «Поручения» → `worker` (`agent.back_office`) → профиль
кабинета → инструменты `/office/mcp` → отчёт в ленте поручений. Неоднозначное или
необратимое агент сначала спрашивает карточкой выбора; ответ мастера — следующий ход.

Без Docker:

```bash
pip install -e '.[dev]'
alembic upgrade head
beauty seed-demo                # демо-мастер alisa (идемпотентно)
beauty api | beauty bot | beauty relay | beauty scheduler | beauty worker
beauty master assign-owner alisa +77011234567   # открыть кабинет мастера этому номеру Telegram
beauty appointment confirm|decline <id>         # решение по заявке из консоли (оператор)
beauty mcp                                      # MCP-сервер beauty-tools (для Hermes)
beauty agent bootstrap | provision|enable|disable <slug>   # ИИ-администратор мастера
```

## Проверки

```bash
ruff check src tests spikes && mypy                    # строгая типизация
pytest tests/unit                                       # без внешних систем
BEAUTY_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/postgres pytest
```

Интеграционные тесты сами создают БД, накатывают миграции Alembic и проверяют:

* оптимистичную блокировку;
* гонку двух одновременных входов нового клиента (уникальный индекс + повтор
  медиатора);
* relay: порядок, частичный сбой, 4 параллельных relay без дублей;
* `LISTEN/NOTIFY`;
* inbox при повторной доставке;
* аренду отложенных задач;
* использование частичного индекса (через `EXPLAIN`);
* сквозной HTTP-сценарий с SSE и кражей refresh-токена;
* tenancy: маппинг агрегата с услугами, гонку за slug, страницу и окна мастера;
* запись в чате через HTTP: заявка, занятое окно и другие окна, подтверждение,
  отклонение, автоотклонение задачей планировщика, отмена и перенос; поток с
  `Last-Event-ID` и `reset`; голосовые по подписанным ссылкам; исключающее ограничение;
* ИИ-администратор: MCP по HTTP настоящим MCP-клиентом (токен профиля, заголовок
  профиля, тикет), запись через инструмент, передача мастеру, `agent_note` не уходит клиенту;
* push: подписки (повтор, чужая, кабинет без прав), уведомления по заявке, подтверждению,
  напоминанию (задача планировщика), передаче вопроса и ответу мастера, удаление исчезнувших
  устройств; шифрование проверяется расшифровкой ключом «браузера»;
* кабинет: поручения через API и поток кабинета, ход по MCP кабинета (подтверждение, выходной,
  сообщение клиенту), вопрос мастеру и ход по его выбору, токен ресепшна не пускает в кабинет;
* ответы API и ошибки (problem+json) — по схемам из `contracts/openapi/beauty.yaml`.

## Дальше

Порядок согласован с владельцем (2026-10-16):

1. ~~Контекст `tenancy`~~ — сделан (страница мастера и окна на реальном API).
2. ~~Запись и переписка клиента~~ — сделаны (клиентский PWA целиком на реальном API).
3. ~~Кабинет мастера~~ — сделан (график, заявки, чаты, поток событий на реальном API).
4. ~~ИИ-администратор ресепшна на Hermes + MCP~~ — сделан (ответы, запись, отмена,
   передача мастеру; короткие тикеты, каталог в инструкциях, ответ итоговым текстом).
5. ~~Поручения мастера ИИ-администратору~~ — сделаны (экран «Поручения» на реальном API:
   график, заявки, отмены, выходные, сообщения клиентам, вопросы карточкой выбора).
6. ~~Push-уведомления и напоминание о визите~~ — сделаны (заявки, подтверждения, отказы,
   сообщения, вопросы агента, ответы на поручения; напоминание за сутки или за 2 ч).
7. ~~Самостоятельная настройка мастера~~ — сделана (профиль, фото, услуги, график с
   перерывами, выходные, правила записи, публикация — в кабинете на реальном API).
8. ~~Расшифровка голосовых~~ — сделана (голосовые клиентов и поручения мастера: OpenRouter
   `/audio/transcriptions`, текст под голосовым, агент отвечает по расшифровке).
9. Подготовка к продакшену: деплой и TLS `*.beautiful.kz`, бэкапы, мониторинг (в том
   числе латентности хода агента), rate limiting.

Параллельно: замер хода агента на реальной модели на рабочем стенде.
