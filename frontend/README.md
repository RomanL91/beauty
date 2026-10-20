# Фронтенд beautiful.kz — три PWA

| Приложение                                       | Адрес (dev)                 | Адрес (docker)               | Прод                  |
| ------------------------------------------------ | --------------------------- | ---------------------------- | --------------------- |
| `apps/client` — страница мастера, вход, чат      | http://alisa.localhost:5173 | http://alisa.localhost:8080  | `<slug>.beautiful.kz` |
| `apps/master` — график, чаты, поручения, клиенты | http://localhost:5174       | http://master.localhost:8080 | `master.beautiful.kz` |
| `apps/admin` — панель хозяина сервиса            | http://localhost:5175       | http://admin.localhost:8080  | `admin.beautiful.kz`  |

Макеты и токены — `docs/design/mockups/`, ТЗ — `docs/tasks/frontend-iteration-1.md`,
отчёт итерации — `docs/frontend/iteration-1-report.md`. Контракт API —
`contracts/openapi/beauty.yaml` (источник правды).

## Быстрый старт

```bash
pnpm -C frontend install
pnpm -C frontend dev                       # оба приложения, mock-режим
VITE_MOCK_AUTH=1 pnpm -C frontend dev      # то же без бэкенда: вход тоже замокан
```

`*.localhost` резолвится в 127.0.0.1 в Chrome/Firefox сам; для Safari добавьте
`127.0.0.1 alisa.localhost` в `/etc/hosts` или откройте `http://localhost:5173/?master=alisa`.

## Режимы API

Моки — те же MSW-обработчики, что в тестах, но **в странице**: `fetch` в `HttpCore`
сначала ищет ответ в обработчиках (`getResponse`), иначе идёт в сеть. Service worker
для моков не нужен, поэтому они уживаются с PWA-worker.

| Переменная              | Значения                                   | Что делает                                                                                |
| ----------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `VITE_API_MODE`         | `mock` (dev) / `real` (prod)               | mock — моки для всего, кроме входа; real — на бэкенд идут группы из `VITE_REAL_API`       |
| `VITE_REAL_API`         | `auth,public,client`, `auth,master`, `all` | какие группы (теги контракта) уже реализованы бэкендом; `all` — моки не загружаются вовсе |
| `VITE_MOCK_AUTH`        | `0` / `1`                                  | в mock-режиме замокать и вход через Telegram (e2e, офлайн-разработка)                     |
| `VITE_DEFAULT_MASTER`   | slug                                       | мастер, если в адресе нет поддомена (только dev)                                          |
| `VITE_VAPID_PUBLIC_KEY` | base64url                                  | публичный ключ Web Push; пусто — подписка недоступна                                      |
| `VITE_API_PROXY`        | URL                                        | куда Vite проксирует `/api` (по умолчанию `http://localhost:8000`)                        |

Бэкенд реализует все группы контракта. Docker-сборки: клиент —
`VITE_REAL_API=auth,public,client,push`, кабинет — `VITE_REAL_API=auth,master,assistant,push`
(группа `master` включает настройки страницы: профиль, услуги, график, правила, фото).
Вход мастера — тот же Telegram
(общий пакет `packages/telegram-login`); если группа `auth` не на бэкенде (моки, e2e),
кабинет открывается заглушкой сессии (`StubMasterAuthGateway`). Кабинет открыт номеру,
привязанному к странице: `BEAUTY_DEMO_OWNER_PHONE` для демо или
`beauty master assign-owner <slug> <телефон>`.

## Структура

```
apps/client, apps/master   app / pages / widgets / features / entities / shared
apps/admin                 app / pages / widgets / shared — desktop-first, графики на SVG
packages/api               типы из контракта (openapi-typescript), HttpCore на openapi-fetch,
                           SSE поверх fetch, порты *Gateway и Http*-адаптеры, модель ленты
packages/mocks             in-memory «бэкенд» с фикстурами по макетам + MSW-обработчики,
                           типизированные контрактом (openapi-msw)
packages/ui                токены, шрифты (@fontsource), компоненты, чат-кит, голосовые
packages/pwa               service worker (precache, network-first для API, push), подписка на push
e2e                        Playwright: сценарии и скриншоты 390×844 (e2e/screenshots)
```

Компоненты зависят только от портов (`AuthGateway`, `MasterGateway`,
`ConversationGateway`, `ScheduleGateway`, `InboxGateway`, `AssistantGateway`,
`MasterEventsGateway`, `MasterSettingsGateway`, `PushGateway`, `ClientsGateway`,
`BroadcastsGateway`, `AdminGateway`); адаптеры собирает `AppContainer`
(`apps/*/src/app/container.ts`) и отдаёт через React context.

Сессия: access-токен только в памяти (`SessionStore`), refresh — httpOnly-cookie;
при 401 — один общий refresh на все параллельные запросы, повтор запроса; отказ refresh
(или 401 после него) — выход и экран входа.

Панель хозяина живёт на своей сессии: httpOnly-cookie `bk_admin` (путь `/api/v1/admin`)
и CSRF-токен в памяти — его возвращают вход и `GET /admin/auth/me`, изменяющие запросы
шлют его в `X-CSRF-Token`. В mock-режиме вход — `owner` / `beauty-admin-2026`.

## Проверки

```bash
pnpm -C frontend lint             # ESLint (+ react-hooks), без предупреждений
pnpm -C frontend format:check     # Prettier
pnpm -C frontend typecheck        # tsc --noEmit во всех пакетах
pnpm -C frontend test             # Vitest: пакеты (Node) и приложения (jsdom)
pnpm -C frontend contract:check   # redocly lint + типы актуальны относительно контракта
pnpm -C frontend e2e              # Playwright на mock-режиме (поднимает все dev-серверы)
```

Изменили контракт → `pnpm -C frontend gen:api`: типы перегенерируются, и всё, что
разошлось с контрактом (адаптеры, моки), перестанет компилироваться.

E2E используют Chromium из Playwright; свой бинарник — `PW_CHROMIUM_PATH=/path/to/chrome`.

## Docker

`docker compose up --build` в корне собирает `frontend/Dockerfile` (три сборки) и
поднимает `web` (nginx, порт 8080): `admin.*` → панель хозяина (noindex), `master.*` → кабинет, `<slug>.*` → страница
мастера, `/api` → сервис `api` (без буферизации — для SSE). Push: передайте
`VITE_VAPID_PUBLIC_KEY` в окружение compose.
