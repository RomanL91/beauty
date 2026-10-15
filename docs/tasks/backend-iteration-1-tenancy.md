# ТЗ: бэкенд, итерация 1 — контекст tenancy и публичная страница мастера

Цель: страница мастера в клиентском PWA работает на реальном API
(`VITE_REAL_API=auth,public`). Контракт — `contracts/openapi/beauty.yaml`
(раздел `public`), фронтенд уже готов.

## 0. Решения по открытым вопросам контракта

Влияют на эту и следующие итерации (вопросы — `docs/frontend/iteration-1-report.md`).

1. **Формат ошибок — RFC 9457 везде.** Единый обработчик отдаёт
   `application/problem+json`: `type`, `title`, `status`, `detail` + расширение `code`
   (машиночитаемый код, как раньше). Identity переводится на тот же формат;
   `ErrorEnvelope` уходит из контракта. Фронтенд понимает оба формата — ломки нет.
2. **SSE с Bearer.** Потоки, требующие сессии, принимают `Authorization: Bearer`
   (фронтенд читает SSE через `fetch`). Токен в query не используем — он попадает в логи.
   Реализуется вместе с перепиской (итерация «переписка»).
3. **`Last-Event-ID`.** Журнал событий потока хранится 24 ч; если присланный id старше
   журнала, сервер шлёт `event: reset`, клиент перечитывает историю. Контракт дополнится
   вместе с перепиской.
4. **SSO между поддоменами.** В проде `BEAUTY_AUTH__COOKIE_DOMAIN=.beautiful.kz`:
   один вход на все страницы мастеров и кабинет. Менять код не нужно.

## 1. Контекст tenancy (`src/beauty/contexts/tenancy`)

Те же слои и приёмы, что в identity: domain / application (CQRS) / infrastructure /
presentation, модуль сборки, императивный маппинг, UoW с outbox, своя схема БД `tenancy`.

### Домен

Агрегат **`Master`** — мастер-арендатор платформы и его публичная страница:

* `slug` (`MasterSlug`): `[a-z0-9-]{2,40}`, не начинается и не заканчивается дефисом,
  не из зарезервированных (`www`, `master`, `api`, `app`, `admin`, …); уникален;
* профиль: `display_name`, `name_forms` (`NameForms`: именительный, родительный,
  дательный), `specialty`, `address`, `about`, `avatar_url`;
* `timezone` (`TimeZoneName`, IANA, проверяется по базе zoneinfo);
* услуги (`Service`, сущность внутри агрегата): название, длительность
  (`ServiceDuration`, 5–480 мин, кратно 5), цена (`Money` в тиынах, KZT) или «по запросу»,
  порядок; архивирование вместо удаления (на услугу будут ссылаться записи);
* `BookingRules`: `confirm_within_hours` (≥ 1), `change_deadline_hours` (≥ 0),
  `min_notice_minutes` (не раньше чем через N минут), `horizon_days` (на сколько дней
  вперёд открыта запись, 1–90), `slot_step_minutes` (шаг сетки окон: 5, 10, 15, 20, 30, 60);
* `WeeklySchedule`: рабочие интервалы по дням недели (локальное время мастера),
  без пересечений; перерыв = промежуток между интервалами;
* выходные даты (`days_off`);
* статус `draft → published` (`unpublish` — обратно). Публичная страница и окна
  видны только у опубликованного мастера; опубликовать можно, только если есть хотя бы
  одна активная услуга и рабочие часы.

События: `MasterRegistered`, `MasterProfileChanged`, `MasterServicesChanged`,
`MasterScheduleChanged`, `MasterPublished`, `MasterUnpublished`
(`tenancy.master.*`, поля — примитивы).

### Свободные окна (доменный сервис `SlotFinder`)

Чистая функция над снимком доступности:

1. Окно поиска `[from, to)` ограничено `now + min_notice` и `today + horizon_days`;
   в ответ попадают окна, которые *начинаются* в `[from, to)`.
2. Для каждого локального дня мастера (с учётом часового пояса и перехода на летнее
   время): рабочие интервалы дня минус выходные даты минус занятые интервалы.
3. Кандидаты — по сетке `slot_step_minutes` от начала интервала; окно подходит, если
   `[start, start + длительность услуги)` целиком внутри свободного интервала.
4. Без указания услуги — по самой короткой активной услуге (`service_id` в ответе).
5. Результат по возрастанию, не больше `limit`.

Занятое время — порт `BusyTimeSource`. В этой итерации записей ещё нет: адаптер
возвращает пустой список; контекст записи подключит свой адаптер, не трогая сервис.

### Приложение

* Команды (для CLI сейчас и кабинета мастера потом): `RegisterMaster`,
  `UpdateMasterProfile`, `AddService`, `UpdateService`, `ArchiveService`,
  `SetWeeklySchedule`, `SetBookingRules`, `SetDaysOff`, `PublishMaster`,
  `UnpublishMaster`.
* Запросы (CQRS, SQL → DTO без агрегатов): `GetMasterPage(slug)`,
  `ListFreeSlots(slug, service_id?, from?, to?, limit)`.
* Ошибки: `master_not_found` (404, в т. ч. для неопубликованного), `service_not_found`
  (404), `slug_taken` (409), `invalid_slot_window` (422), доменные — 422.

### API (presentation)

* `GET /api/v1/masters/{slug}` → `MasterPage` (контракт).
* `GET /api/v1/masters/{slug}/slots?service&from&to&limit` → `{items: Slot[]}`;
  время — RFC 3339 в поясе мастера.
* Публичные эндпоинты кэшируемы: `Cache-Control: public, max-age=60` для страницы,
  `no-store` для окон.

### Данные

Схема `tenancy`: `masters` (профиль, правила, статус, `version` для оптимистичной
блокировки; недельное расписание, выходные даты и фото портфолио — JSONB: это
value objects агрегата, читаются и пишутся целиком, отдельные таблицы не нужны) и
`master_services`. Индексы: уникальный `slug`; услуги — по `(master_id, position)`
частично для неархивных. Миграция Alembic `0002`.

### Демо-данные

`beauty seed-demo` — идемпотентно создаёт и публикует мастера `alisa` с услугами и
расписанием как в макетах. В `docker-compose.yml` — одноразовый сервис `seed` после
`migrate`.

## 2. Фронтенд

* Docker-сборка клиента: `VITE_REAL_API=auth,public`.
* Моки identity — тоже problem+json (как сервер).

## 3. Качество

* Unit: value objects, агрегат (инварианты, события), `SlotFinder` (сетка, перерывы,
  выходные, min notice, горизонт, переход на летнее время, услуга по умолчанию),
  обработчики команд и запросов на in-memory двойниках.
* Интеграционные (PostgreSQL): репозиторий и маппинг агрегата с услугами, оптимистичная
  блокировка, уникальность slug, HTTP-сценарий страницы и окон, неопубликованный мастер
  → 404, problem+json.
* Контракт: ответы API проверяются по `contracts/openapi/beauty.yaml` в интеграционном
  тесте (валидатор JSON Schema по схемам компонентов).
* `ruff`, `mypy --strict`, unit + integration зелёные.

## Критерии приёмки

* `docker compose up` → `http://alisa.localhost:8080` показывает страницу мастера и окна
  с реального API (моки — только переписка);
* формат ошибок — problem+json на всех эндпоинтах, контракт обновлён и валиден;
* все проверки зелёные.
