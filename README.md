# Beauty — персональный ИИ-администратор мастера

Мастер-одиночка (массаж, ногти, брови, косметология) получает администратора, как
в салоне: тот ведёт переписку с клиентами, запись и график, помнит клиентов и
выполняет поручения мастера. Клиент приходит на страницу мастера
(`alisa-cosmetolog.beautiful.kz`, PWA) и общается в чате, а отвечает ему агент
мастера.

Этот репозиторий — первый вертикальный срез:

* **shared kernel** — фундамент всех контекстов;
* **контекст `identity`** — глобальный аккаунт клиента и вход через Telegram;
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
├── bootstrap/                      # корень композиции (Pure DI), каталог схемы
└── entrypoints/                    # процессы: api, bot, relay, scheduler
migrations/                         # Alembic (async)
spikes/hermes/                      # кит спайка Hermes (см. его README)
tests/unit | tests/integration      # 104 теста; интеграционные — на реальном PostgreSQL
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
docker compose up --build       # postgres, rabbitmq, migrate, api, bot, relay, scheduler, web
# API: http://localhost:8000/api/v1/docs
# PWA клиента: http://alisa.localhost:8080 · кабинет мастера: http://master.localhost:8080
```

Фронтенд (два PWA, контракт API, моки) — `frontend/README.md`.

Без Docker:

```bash
pip install -e '.[dev]'
alembic upgrade head
beauty api | beauty bot | beauty relay | beauty scheduler
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
* сквозной HTTP-сценарий с SSE и кражей refresh-токена.

## Дальше

1. Прогнать спайк Hermes (`spikes/hermes/README.md`): по его итогам фиксируем
   адаптер `AgentRuntime` (один экземпляр или пул с шардированием мастеров).
2. Контекст `tenancy`: мастер, страница-поддомен, `BookingPolicy`.
3. Контексты `catalog`, `crm` и `scheduling`: исключающее ограничение `EXCLUDE
   USING gist` против двойной записи, `SlotSwapProcess`.
