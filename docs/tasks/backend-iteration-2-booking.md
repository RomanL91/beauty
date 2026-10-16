# ТЗ: бэкенд, итерация 2 — запись и переписка клиента

Цель: клиентский PWA целиком работает на реальном API
(`VITE_REAL_API=auth,public,client`). Клиент записывается из чата, видит заявку,
её подтверждение или отклонение, отменяет и переносит запись; окна на странице мастера
учитывают занятое время. Контракт — `contracts/openapi/beauty.yaml`, раздел `client`.

Вне итерации: ИИ-агент (свободный текст и голосовые остаются без автоответа;
расшифровки нет), кабинет мастера и его вход (подтверждает и отклоняет мастер пока из
CLI), push.

## 0. Решения

1. **Запись идёт через чат.** Клиент шлёт намерение (`book_slot`, `slot_pick`,
   новое `request_slots`), «администратор записи» отвечает карточкой заявки или
   предложением окон. Сейчас это детерминированный обработчик намерений, а не LLM; агент
   следующей итерации встанет на то же место — на событие «клиент написал».
2. **Новое намерение `request_slots`** (`{client_id, kind, text, service_id?}`): «хочу
   записаться, какое время свободно?» со страницы мастера. В ленте — текст клиента,
   в ответ — `slot_offer` на ближайший день с окнами. Раньше фронтенд слал это свободным
   текстом, который без агента остался бы без ответа.
3. **Занятое окно** при `book_slot`/`slot_pick` — не ошибка запроса: сообщение клиента
   принято (201), администратор отвечает «это время уже заняли» и новым `slot_offer`
   (открытый вопрос 11). Повторный выбор из уже использованного предложения — 409
   `offer_already_used`.
4. **Перенос** — как в контракте: новая заявка на новое время со ссылкой на старую
   запись; старая освобождается, только когда мастер подтвердит новую. Если новую
   отклонили или она истекла, старая запись остаётся в силе. Новое время, пересекающееся
   со старым, — 409 `slot_taken` (окна для переноса и так его не показывают).
5. **Удержание окна** = `confirm_within_hours`; `hold_until` и `auto_decline_at`
   совпадают (открытый вопрос 16 — поля оставляем, значения равны). Истёкшая заявка
   отклоняется задачей планировщика (`cancelled_by: system`).
6. **Отмена и перенос клиентом** — не позднее `change_deadline_hours` до начала,
   иначе 409 `change_deadline_passed`.
7. **Поток переписки**: у каждой переписки свой счётчик событий; `id` кадра — номер
   события. Журнал хранится 24 ч. Если `Last-Event-ID` старше журнала — кадр
   `event: reset` (`{"type": "reset"}`), клиент перечитывает историю (решение 3 итерации 1;
   добавляется в контракт).
8. **Голосовые** сохраняются в файловое хранилище; `audio_url` — подписанная ссылка
   `/api/v1/media/…?exp&sig` (HMAC, 1 ч): `<audio>` не умеет слать `Authorization`
   (открытый вопрос 7). `transcript` — `null` до итерации агента.
9. **Клиент в записи** (`ClientRef`) — снимок на момент заявки: имени у аккаунта пока нет,
   поэтому «Новый клиент · …12 34» и маскированный телефон; `visit_number` — номер
   визита к этому мастеру (подтверждённые и завершённые записи до этой + 1).

## 1. Контекст booking (`src/beauty/contexts/booking`)

### Домен

Агрегат **`Appointment`** — запись клиента к мастеру:

* `master_id`, `client_id` (аккаунт identity), снимок услуги (`id`, название,
  длительность, цена), снимок клиента (`ClientRef`), `start`/`end` (UTC);
* статусы: `requested → confirmed → completed`; `requested → cancelled`
  (`declined` мастером, `expired` — системой, отозвана клиентом);
  `confirmed → cancelled` (клиент до дедлайна, мастер);
* `hold_until`, `confirmed_at`, `cancelled_at`, `cancelled_by` (`client|master|system`),
  `cancel_reason` (`client_cancelled`, `declined`, `expired`, `rescheduled`),
  `change_deadline` (из правил мастера на момент заявки), `reschedule_of`;
* события `booking.appointment.requested|confirmed|cancelled|completed` — с полным
  снимком записи для подписчиков (карточка в чате).

Инвариант «одно время — одна запись» держит БД: `EXCLUDE USING gist (master_id WITH =,
tstzrange(start_at, end_at) WITH &&) WHERE status IN ('requested','confirmed')`.
Нарушение → `slot_taken` (409).

### Приложение

* `RequestAppointment(master_id, client_id, service_id, start, reschedule_of?)`:
  проверяет окно у tenancy (порт `SlotPolicy`: окно свободно по расписанию, правилам и
  занятости; даёт снимок услуги и правила), снимок клиента (порт `ClientDirectory` →
  identity), сохраняет заявку и ставит задачу автоотклонения.
* `ConfirmAppointment`, `DeclineAppointment` (мастер; пока CLI),
  `CancelAppointment` (клиент), `RescheduleAppointment` (клиент),
  `ExpireAppointment`, `CompleteAppointment` (задачи планировщика).
* Запрос `GetAppointment(id, client_id)` — для ответов API.
* Адаптер `BusyTimeSource` для tenancy: заявки и подтверждённые записи мастера.

### API

* `POST /appointments/{id}/cancel` → `Appointment`;
* `POST /appointments/{id}/reschedule` → новая заявка (`Appointment`);
* чужая или несуществующая запись — 404 `appointment_not_found`.

### CLI

`beauty appointment confirm|decline <id>` — действия мастера до кабинета.

## 2. Контекст conversations (`src/beauty/contexts/conversations`)

### Домен

* **`Conversation`** — переписка клиента с мастером (одна на пару, уникальна);
  счётчик событий потока.
* **`Message`** — отдельный агрегат (история не грузится в переписку целиком): автор,
  `client_id` (идемпотентность, уникален в переписке), содержимое по видам: `text`,
  `voice`, `slot_offer` (окна, `selected_start`), `booking_card` (снимок записи с
  версией), `system` (тон). Изменения — `select_slot`, `refresh_appointment`
  (старый снимок не перетирает новый).

### Приложение

* `OpenConversation(master_slug, client_id)` (идемпотентно), `GetMyConversation`.
* `PostClientMessage` — текст, голосовое, `slot_pick`, `book_slot`, `request_slots`;
  повтор с тем же `client_id` возвращает то же сообщение. Событие
  `conversations.message.client_posted` с намерением.
* **Администратор записи** (`BookingAssistant`, консьюмер события выше):
  `book_slot`/`slot_pick` → `RequestAppointment` → карточка; занято → «уже заняли» +
  окна; `request_slots` → окна на ближайший день.
* **Реакция на запись** (консьюмер `booking.appointment.*`): обновить карточки,
  системное сообщение («Запись подтверждена», «Мастер не сможет принять в это время»,
  «Заявка не подтверждена вовремя», «Запись отменена»), карточка новой заявки при
  переносе.
* Запросы: `ListMessages(conversation_id, client_id, before, limit)`.

### Поток событий (SSE)

`GET /conversations/{id}/events` с `Authorization: Bearer`: журнал
`conversations.feed_events` (`conversation_id`, `seq`, тип, `message_id`), строка
журнала и outbox-событие пишутся в транзакции изменения сообщения; номер — счётчик
переписки под блокировкой строки (порядок номеров = порядок коммитов). Realtime-мост
будит поток, поток дочитывает журнал после последнего номера; если мост недоступен —
опрос раз в `sse_poll_interval`. Пинги, `retry: 3000`, ограничение длительности.

### API

`GET|POST /conversations/me?master=`, `GET|POST /conversations/{id}/messages`
(JSON и multipart), `GET /conversations/{id}/events`, `GET /media/{key}?exp&sig`.

## 3. Инфраструктура

* Роль процесса `beauty worker` — консьюмеры контекстов (очереди с повторами и DLQ,
  inbox); сервис `worker` в docker compose. Обработчики задач booking — в `scheduler`.
* Bearer-аутентификация клиента — общая зависимость FastAPI поверх
  `JwtAccessTokenVerifier`.
* Миграция `0003`: схемы `booking` и `conversations`, расширение `btree_gist`.

## 4. Фронтенд

* Docker-сборка клиента: `VITE_REAL_API=auth,public,client`.
* Намерение `request_slots` вместо свободного текста при записи со страницы мастера;
  моки — так же.
* Кадр `reset` → перечитать историю.

## 5. Качество

* Unit: агрегаты (переходы, дедлайн, удержание), обработчики на in-memory двойниках,
  администратор записи, рендеринг текстов.
* Интеграционные (PostgreSQL): исключающее ограничение и гонка двух заявок на одно окно,
  окна tenancy с учётом занятости, сценарий «вход → переписка → book_slot → карточка →
  подтверждение → отмена» через HTTP и обработчики событий, поток с `Last-Event-ID` и
  `reset`, идемпотентность `client_id`, автоотклонение по задаче, ответы по схемам контракта.
* `ruff`, `mypy --strict`, unit + integration, фронтенд — lint, typecheck, unit,
  `contract:check`.

## Критерии приёмки

* `docker compose up` → на `http://alisa.localhost:8080` вход, выбор окна, заявка в чате;
  `beauty appointment confirm <id>` — карточка в чате становится «Запись подтверждена»
  без перезагрузки; окно пропадает со страницы мастера;
* отмена и перенос из «Мои записи» работают на реальном API;
* контракт обновлён и валиден, все проверки зелёные.
