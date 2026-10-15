# ТЗ: фронтенд, итерация 1 — два PWA по макетам (клиент и мастер)

Референс: docs/design/mockups/ (README.md — токены, маршруты, решения; *.dc.html —
макеты экранов, переносить визуал и тексты, НЕ код). Отклонения от макетов — только
осознанные и перечисленные в отчёте.

## 0. Стек и структура
- frontend/ — pnpm workspace:
  - apps/client   — PWA клиента (страница мастера на поддомене)
  - apps/master   — PWA мастера (дашборд)
  - packages/ui   — токены (CSS custom properties из README), базовые компоненты
  - packages/api  — типы и клиент из OpenAPI (openapi-typescript + openapi-fetch)
  - packages/mocks — MSW-обработчики и фикстуры по контракту
- React + TypeScript (strict, noUncheckedIndexedAccess) + Vite, react-router (data
  router), TanStack Query для серверного состояния, без глобального стора.
- Архитектура слоёв (Feature-Sliced): app / pages / widgets / features / entities /
  shared. Доступ к API — через порты-интерфейсы (MasterGateway, ConversationGateway,
  ScheduleGateway, AuthGateway) и классы-адаптеры над openapi-fetch; адаптеры
  внедряются через один AppContainer (React context), компоненты знают только порты.
- Шрифты Unbounded и Manrope — локально (@fontsource), чтобы PWA работал офлайн.
- Версии зависимостей — актуальные стабильные, зафиксированы в lockfile.

## 1. Контракт API — contracts/openapi/beauty.yaml (источник правды; бэкенд реализует позже)
Уже существующее (описать точно по коду src/beauty/contexts/identity/presentation/api):
- POST /api/v1/auth/telegram/challenges
- GET  /api/v1/auth/telegram/challenges/{id}
- GET  /api/v1/auth/telegram/challenges/{id}/events   (SSE)
- POST /api/v1/auth/telegram/challenges/{id}/session
- POST /api/v1/auth/session/refresh, POST /api/v1/auth/session/logout
- (cookie bk_auth_challenge / bk_refresh, httpOnly — фронт их не читает).

Новое (только контракт + MSW):
- публичное: GET /masters/{slug} (профиль, услуги, правила записи), GET /masters/{slug}/slots?service&from&to
- клиент: GET/POST /conversations/me?master={slug}, GET /conversations/{id}/messages?before&limit,
  POST /conversations/{id}/messages (text | voice multipart), GET /conversations/{id}/events (SSE,
  Last-Event-ID), POST /appointments/{id}/cancel, POST /appointments/{id}/reschedule
- мастер: GET /me/schedule?date, POST /me/appointments/{id}/confirm|decline,
  GET /me/conversations?filter=needs_me|agent|me&q, GET /me/conversations/{id}/messages,
  POST /me/conversations/{id}/messages, PUT /me/conversations/{id}/handler {agent|master},
  GET/POST /me/assistant/messages (text | voice), POST /me/assistant/choices/{choiceId},
  GET /me/events (SSE: новые сообщения, заявки, статусы)
- push: POST /push/subscriptions, DELETE /push/subscriptions/{id}

Модель сообщения — размеченное объединение по kind: text | voice{audio_url, duration,
transcript} | slot_offer{slots[]} | booking_card{appointment} | system | agent_note
(только мастеру) | choice{options[]} | task_progress{steps[]}; поля author
(client|agent|master), ai_generated, sources[{title,url}], created_at, id (UUIDv7).
Статусы записи: requested(hold_until, auto_decline_at) | confirmed | cancelled | completed.
Ошибки — RFC 9457 problem+json.

## 2. Клиентское приложение (apps/client)
- Мастер определяется по поддомену <slug>.beautiful.kz; в dev — <slug>.localhost
  или ?master=<slug>. Резолвер — отдельный класс MasterSlugResolver (стратегии по среде).
- Экраны Main, ClientLogin, ClientChat — по макетам, все состояния: загрузка
  (скелетоны), пусто, ошибка, офлайн.
- Вход — реальный API: старт challenge → показать код и таймер до истечения → SSE
  статуса (с переподключением; при обрыве — опрос GET) → обмен на сессию → возврат на
  экран, с которого начат вход (запись в выбранный слот продолжается автоматически).
  Access-токен только в памяти; refresh — single-flight при 401 (параллельные
  запросы ждут один refresh); при reuse/401 после refresh — выход и экран входа.
- Чат: оптимистичная отправка (pending → sent → failed с повтором), SSE с
  Last-Event-ID и дедупликацией по id, подгрузка истории вверх, пометка «Ответ ИИ» и
  источники, выбор слота кнопкой из slot_offer, карточка заявки с таймером удержания.
- Голосовые: MediaRecorder (webm/opus, fallback mp4/aac для iOS Safari), удержание
  для записи + отмена свайпом, лимит длительности, превью перед отправкой.

## 3. Приложение мастера (apps/master)
- Вход мастера в этой итерации — MSW-заглушка (роль мастера появится с контекстом
  tenancy); интерфейс AuthGateway общий, подмена только адаптера.
- Экраны MasterSchedule, MasterChats, MasterDialog, MasterAssistant + нижняя навигация.
- График: неделя, свайп/стрелки по дням, заявки с обратным отсчётом до автоотклонения
  (тикает локально от auto_decline_at, сверяется с сервером по SSE), подтвердить/отклонить
  с оптимистичным обновлением и откатом.
- Диалог: переключатель «Агент / Я» (PUT handler); отправка мастером автоматически
  переводит на «Я» с уведомлением; agent_note — отдельный стиль, «видите только вы».
- Поручения: голос (удержание большой кнопки) и текст, карточки choice с выбором,
  task_progress обновляется по SSE.
- Широкий экран: колонка до 480 px по центру.

## 4. PWA
- vite-plugin-pwa для обоих приложений: манифест (имя, иконки-заглушки, theme
  #7A2E57), офлайн-оболочка, кэш статики; данные — network-first.
- Web Push: экран/плашка запроса разрешения (не при первом заходе, а после записи
  или в настройках), подписка с VAPID-ключом из env, отправка на /push/subscriptions,
  обработчики push и notificationclick в service worker (открыть нужный чат/день).
  На iOS — подсказка «добавьте на экран Домой», если push недоступен вне PWA.

## 5. Окружение
- Dev: Vite proxy /api → http://localhost:8000; режим VITE_API_MODE=mock|real
  (mock — MSW для всего, кроме входа; real — реальные эндпоинты, где они есть).
- Docker: сервис web (nginx) раздаёт обе сборки; client по host-шаблону *.beautiful.kz,
  master по отдельному host (master.beautiful.kz); /api проксируется на api. Добавить в
  корневой docker-compose.yml.

## 6. Качество
- ESLint + Prettier, tsc --noEmit без ошибок; русские комментарии/JSDoc у публичных
  модулей, портов и адаптеров.
- Vitest + Testing Library: адаптеры gateway (на MSW), single-flight refresh,
  редьюсер сообщений (оптимистичные, дедуп SSE), таймер автоотклонения.
- Playwright e2e на mock-режиме: (а) клиент: страница → «Записаться» → вход (MSW
  подтверждает challenge) → чат → выбор слота → карточка заявки; (б) мастер: график →
  подтвердить заявку; (в) диалог → «Я» → отправка; (г) поручение → выбор варианта →
  прогресс. Скриншоты экранов 390×844 сохранить в frontend/e2e/screenshots/ для сверки
  с макетами.
- Доступность: кнопки/ссылки нативные, aria-label у иконок, фокус-стили, контраст как
  в макетах, зона нажатия ≥ 44 px.

## Критерии приёмки
- `pnpm -C frontend install && pnpm -C frontend dev` поднимает оба приложения в mock-режиме;
  все 7 экранов визуально соответствуют макетам (скриншоты e2e приложены к отчёту);
- вход через Telegram работает против реального бэкенда из docker compose (живой бот);
- contracts/openapi/beauty.yaml валиден (redocly lint), типы packages/api сгенерированы
  из него, MSW-обработчики типизированы теми же типами (расхождение = ошибка компиляции);
- lint, typecheck, unit и e2e зелёные; `docker compose up` раздаёт обе сборки через nginx;
- отчёт: что отклонено от макетов и почему, открытые вопросы к контракту API.
