import type {
  Appointment,
  ChallengeStatus,
  ClientMessageInput,
  ConversationFilter,
  ConversationSummary,
  DaySchedule,
  Handler,
  Message,
  MessageOf,
  MessagePage,
  ScheduleItem,
  Service,
  SessionResponse,
  Slot,
  StartChallengeResponse,
} from '@beauty/api';
import {
  addDays,
  at,
  fromNow,
  hhmm,
  humanDate,
  localDate,
  minutesBetween,
  onDate,
  weekday,
} from './clock';

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
import { EventLog } from './event-log';
import { MockProblem } from './errors';
import { MockSettings } from './settings';
import { uuidv7 } from './ids';
import { CLIENT_CONVERSATION_ID, clientChatSeed } from './fixtures/client-chat';
import {
  CONVERSATIONS,
  appointmentsSeed,
  assistantSeed,
  daryaDialogSeed,
  inboxSeed,
  otherDialogsSeed,
  type BreakEntry,
} from './fixtures/master-cabinet';
import { DEMO_SLUG, SERVICES, masterPage } from './fixtures/master-page';
import { CLIENTS, ME_CLIENT } from './fixtures/people';
import { base, bookingCard, slotFor, slotOffer, system, text, voice } from './fixtures/messages';

/** Хранилище «cookie» мок-сессии (в браузере — localStorage, в тестах — память). */
export interface KeyValueStore {
  get(key: string): string | null;
  set(key: string, value: string): void;
  remove(key: string): void;
}

export { MockProblem };

/** Хранилище в памяти. */
export function memoryStore(): KeyValueStore {
  const map = new Map<string, string>();
  return {
    get: (k) => map.get(k) ?? null,
    set: (k, v) => void map.set(k, v),
    remove: (k) => void map.delete(k),
  };
}

/** Настройки поведения моков. */
export interface MockDbOptions {
  /** Задержка ответов агента, мс. */
  readonly agentDelayMs?: number;
  /** Шаг сценария входа (pending → claimed → confirmed → completed), мс. */
  readonly challengeStepMs?: number;
  /** Шаг прогресса поручения, мс. */
  readonly taskStepMs?: number;
  readonly storage?: KeyValueStore;
}

interface MockChallenge {
  readonly id: string;
  readonly code: string;
  readonly createdAt: number;
  readonly expiresAt: number;
  consumed: boolean;
}

const SESSION_KEY = 'beauty-mock-session';
const CHALLENGE_TTL_MS = 5 * 60_000;
const CLIENT_ACCOUNT_ID = '0192a0c0-0000-7000-8000-00000000c11e';

/**
 * Состояние моков и сценарии «бэкенда»: вход, агент клиента, кабинет мастера.
 *
 * Все изменения публикуются в журналы событий (`clientLog`, `masterLog`),
 * которые отдают SSE-обработчики.
 */
export class MockDb {
  readonly page = masterPage();
  readonly settings = new MockSettings(this.page, (file) => this.#storeUpload(file));
  readonly clientLog = new EventLog();
  readonly masterLog = new EventLog();

  readonly #opts: Required<Omit<MockDbOptions, 'storage'>>;
  readonly #storage: KeyValueStore;
  readonly #timers = new Set<ReturnType<typeof setTimeout>>();
  readonly #challenges = new Map<string, MockChallenge>();
  readonly #uploads = new Map<string, Blob>();

  #clientMessages: Message[];
  readonly #clientAppointments = new Map<string, Appointment>();

  readonly #appointments = new Map<string, Appointment>();
  readonly #breaks: BreakEntry[];
  readonly #inbox = new Map<string, ConversationSummary>();
  readonly #dialogs = new Map<string, Message[]>();
  #assistant: Message[];

  constructor(options: MockDbOptions = {}) {
    this.#opts = {
      agentDelayMs: options.agentDelayMs ?? 700,
      challengeStepMs: options.challengeStepMs ?? 1200,
      taskStepMs: options.taskStepMs ?? 1500,
    };
    this.#storage = options.storage ?? memoryStore();

    const chat = clientChatSeed();
    this.#clientMessages = chat.messages;
    this.#clientAppointments.set(chat.appointment.id, chat.appointment);

    const { appointments, breaks } = appointmentsSeed();
    for (const a of appointments) this.#appointments.set(a.id, a);
    this.#breaks = breaks;
    for (const c of inboxSeed()) this.#inbox.set(c.id, c);
    const daryaRequest = appointments.find(
      (a) => a.client.id === CLIENTS.darya.id && a.status === 'requested',
    );
    this.#dialogs.set(CONVERSATIONS.darya, daryaRequest ? daryaDialogSeed(daryaRequest) : []);
    for (const [id, messages] of Object.entries(otherDialogsSeed()))
      this.#dialogs.set(id, messages);
    this.#assistant = assistantSeed();
  }

  /** Шаг сценария входа, мс (обработчик SSE опрашивает чаще). */
  get challengeStepMs(): number {
    return this.#opts.challengeStepMs;
  }

  /** Остановить таймеры сценариев (для тестов). */
  dispose(): void {
    for (const t of this.#timers) clearTimeout(t);
    this.#timers.clear();
    for (const url of this.#uploads.keys()) URL.revokeObjectURL(url);
  }

  // ───────────────────────────── вход ─────────────────────────────

  startChallenge(): StartChallengeResponse {
    const id = uuidv7();
    const now = Date.now();
    const challenge: MockChallenge = {
      id,
      code: String(10 + Math.floor(Math.random() * 90)),
      createdAt: now,
      expiresAt: now + CHALLENGE_TTL_MS,
      consumed: false,
    };
    this.#challenges.set(id, challenge);
    return {
      challenge_id: id,
      deep_link: `https://t.me/beautiful_kz_bot?start=mock-${id.slice(-8)}`,
      confirmation_code: challenge.code,
      expires_at: new Date(challenge.expiresAt).toISOString(),
    };
  }

  /** Статус входа: сценарий идёт сам по времени с момента старта. */
  challengeStatus(id: string): { status: ChallengeStatus; expiresAt: string } {
    const c = this.#challenges.get(id);
    if (!c) throw new MockProblem(404, 'challenge_not_found', 'Вход не найден');
    const expiresAt = new Date(c.expiresAt).toISOString();
    if (c.consumed) return { status: 'consumed', expiresAt };
    const now = Date.now();
    if (now >= c.expiresAt) return { status: 'expired', expiresAt };
    const steps: ChallengeStatus[] = ['pending', 'claimed', 'confirmed', 'completed'];
    const index = Math.min(
      Math.floor((now - c.createdAt) / this.#opts.challengeStepMs),
      steps.length - 1,
    );
    return { status: steps[index] ?? 'pending', expiresAt };
  }

  exchangeChallenge(id: string): SessionResponse {
    const { status } = this.challengeStatus(id);
    if (status === 'expired') throw new MockProblem(410, 'challenge_expired', 'Вход истёк');
    if (status !== 'completed')
      throw new MockProblem(409, 'invalid_challenge_state', 'Вход ещё не завершён');
    const c = this.#challenges.get(id);
    if (c) c.consumed = true;
    this.#storage.set(SESSION_KEY, CLIENT_ACCOUNT_ID);
    return this.#session();
  }

  refreshSession(): SessionResponse | null {
    return this.#storage.get(SESSION_KEY) ? this.#session() : null;
  }

  logout(): void {
    this.#storage.remove(SESSION_KEY);
  }

  #session(): SessionResponse {
    return {
      account_id: this.#storage.get(SESSION_KEY) ?? CLIENT_ACCOUNT_ID,
      access_token: `mock-access-${uuidv7().slice(-12)}`,
      token_type: 'Bearer',
      expires_at: fromNow(15 * 60_000),
    };
  }

  // ───────────────────────── страница мастера ─────────────────────────

  getPage(slug: string): ReturnType<typeof masterPage> {
    if (slug !== DEMO_SLUG || !this.settings.published)
      throw new MockProblem(404, 'master_not_found', 'Мастер не найден');
    return this.page;
  }

  /** Свободные окна: детерминированный набор по дням, минус занятые клиентом. */
  listSlots(
    slug: string,
    query: { service?: string | null; from?: string | null; to?: string | null; limit?: number },
  ): Slot[] {
    this.getPage(slug);
    const service = this.#service(query.service ?? null);
    const from = query.from ? Date.parse(query.from) : Date.now();
    const to = query.to ? Date.parse(query.to) : Date.now() + 14 * 86_400_000;
    const taken = new Set(
      [...this.#clientAppointments.values()]
        .filter((a) => a.status !== 'cancelled')
        .map((a) => Date.parse(a.start)),
    );
    const patterns = [
      ['18:00'],
      ['12:00', '15:30', '18:00'],
      ['10:00', '12:00'],
      ['12:00', '15:30'],
      ['10:00', '16:00'],
    ];
    const slots: Slot[] = [];
    for (let day = 0; day < 21 && slots.length < (query.limit ?? 20); day += 1) {
      const date = localDate(day);
      if (this.settings.isDayOff(date)) continue;
      const times =
        day === 0 ? patterns[0]! : patterns[(weekday(date) % (patterns.length - 1)) + 1]!;
      for (const hm of times) {
        const slot = slotFor(service, at(date, hm));
        const start = Date.parse(slot.start);
        if (start <= from || start >= to || taken.has(start)) continue;
        slots.push(slot);
      }
    }
    return slots.slice(0, query.limit ?? 20);
  }

  #service(id: string | null): Service {
    const found = this.page.services.find((s) => s.id === id);
    return found ?? SERVICES.backMassage;
  }

  // ─────────────────────────── чат клиента ───────────────────────────

  get clientConversationId(): string {
    return CLIENT_CONVERSATION_ID;
  }

  clientConversation(slug: string): { id: string; master_slug: string } {
    this.getPage(slug);
    return { id: CLIENT_CONVERSATION_ID, master_slug: slug };
  }

  clientMessages(conversationId: string, before: string | null, limit: number): MessagePage {
    this.#ensureClientConversation(conversationId);
    return page(this.#clientMessages, before, limit);
  }

  /** Сообщение клиента (текст или выбор окна) и ответ агента. */
  sendClientMessage(conversationId: string, input: ClientMessageInput): Message {
    this.#ensureClientConversation(conversationId);
    const existing = this.#clientMessages.find((m) => m.client_id === input.client_id);
    if (existing) return existing;

    if (input.kind === 'slot_pick')
      return this.#pickSlot(input.client_id, input.offer_id, input.start);
    if (input.kind === 'book_slot')
      return this.#bookSlot(input.client_id, input.service_id, input.start);
    if (input.kind === 'request_slots') {
      const asked = text(
        base('client', new Date().toISOString(), { clientId: input.client_id }),
        input.text,
      );
      this.#pushClient(asked);
      this.#later(() => this.#offerSlots(this.#service(input.service_id ?? null)));
      return asked;
    }

    const message = text(
      base('client', new Date().toISOString(), { clientId: input.client_id }),
      input.text,
    );
    this.#pushClient(message);
    this.#later(() => this.#agentAnswer(input.text));
    return message;
  }

  /** Голосовое клиента: расшифровка придёт позже обновлением сообщения. */
  sendClientVoice(
    conversationId: string,
    clientId: string,
    audio: Blob,
    duration: number,
  ): Message {
    this.#ensureClientConversation(conversationId);
    const existing = this.#clientMessages.find((m) => m.client_id === clientId);
    if (existing) return existing;
    const message = voice(
      base('client', new Date().toISOString(), { clientId }),
      duration,
      null,
      this.#storeUpload(audio),
    );
    this.#pushClient(message);
    this.#later(() => {
      const transcribed: Message = { ...message, transcript: 'Можно перенести запись на вечер?' };
      this.#replaceClient(transcribed);
      this.#later(() =>
        this.#pushClient(
          text(
            base('agent', new Date().toISOString()),
            'Могу предложить вечерние окна — напишите удобный день, и я покажу свободное время.',
          ),
        ),
      );
    });
    return message;
  }

  cancelClientAppointment(id: string): Appointment {
    const current = this.#clientAppointments.get(id);
    if (!current) throw new MockProblem(404, 'appointment_not_found', 'Запись не найдена');
    if (current.status === 'cancelled') return current;
    const cancelled: Appointment = {
      ...stripStatus(current),
      status: 'cancelled',
      cancelled_by: 'client',
    };
    this.#updateClientAppointment(cancelled);
    this.#later(() =>
      this.#pushClient(
        system(
          base('agent', new Date().toISOString()),
          'Запись отменена. Окно освобождено.',
          'info',
        ),
      ),
    );
    return cancelled;
  }

  rescheduleClientAppointment(id: string, start: string): Appointment {
    const current = this.#clientAppointments.get(id);
    if (!current) throw new MockProblem(404, 'appointment_not_found', 'Запись не найдена');
    const slot = slotFor(current.service, start);
    const moved: Appointment = {
      ...stripStatus(current),
      start: slot.start,
      end: slot.end,
      status: 'requested',
      hold_until: fromNow(2 * 3600_000),
      auto_decline_at: fromNow(2 * 3600_000),
    };
    this.#updateClientAppointment(moved);
    return moved;
  }

  #pickSlot(clientId: string, offerId: string, start: string): Message {
    const offer = this.#clientMessages.find(
      (m): m is MessageOf<'slot_offer'> => m.id === offerId && m.kind === 'slot_offer',
    );
    if (!offer) throw new MockProblem(404, 'offer_not_found', 'Предложение не найдено');
    const slot = offer.slots.find((s) => s.start === start);
    if (!slot) throw new MockProblem(422, 'slot_not_offered', 'Этого окна нет в предложении');
    if (offer.selected_start !== null)
      throw new MockProblem(409, 'offer_already_used', 'Окно уже выбрано');

    this.#replaceClient({ ...offer, selected_start: start });
    const message = text(base('client', new Date().toISOString(), { clientId }), hhmm(start));
    this.#pushClient(message);

    const service = this.#service(slot.service_id ?? null);
    const appointment: Appointment = {
      id: uuidv7(),
      status: 'requested',
      service,
      start: slot.start,
      end: slot.end,
      client: ME_CLIENT,
      hold_until: fromNow(this.page.booking_rules.confirm_within_hours * 3600_000),
      auto_decline_at: fromNow(this.page.booking_rules.confirm_within_hours * 3600_000),
    };
    this.#clientAppointments.set(appointment.id, appointment);
    this.#later(() =>
      this.#pushClient(bookingCard(base('agent', new Date().toISOString()), appointment)),
    );
    return message;
  }

  /** Запрос конкретного окна (после входа со страницы мастера). */
  #bookSlot(clientId: string, serviceId: string, start: string): Message {
    const service = this.#service(serviceId);
    const message = text(
      base('client', new Date().toISOString(), { clientId }),
      `Хочу записаться: ${service.title.toLowerCase()}, ${humanDate(start.slice(0, 10))} в ${hhmm(start)}`,
    );
    this.#pushClient(message);
    const free = this.listSlots(DEMO_SLUG, { service: service.id, limit: 60 }).find(
      (s) => Date.parse(s.start) === Date.parse(start),
    );
    if (!free) {
      this.#later(() => this.#agentAnswer(`запись ${service.title}`));
      return message;
    }
    const appointment: Appointment = {
      id: uuidv7(),
      status: 'requested',
      service,
      start: free.start,
      end: free.end,
      client: ME_CLIENT,
      hold_until: fromNow(this.page.booking_rules.confirm_within_hours * 3600_000),
      auto_decline_at: fromNow(this.page.booking_rules.confirm_within_hours * 3600_000),
    };
    this.#clientAppointments.set(appointment.id, appointment);
    this.#later(() =>
      this.#pushClient(bookingCard(base('agent', new Date().toISOString()), appointment)),
    );
    return message;
  }

  #agentAnswer(question: string): void {
    const wantsBooking = /запис|окн|свобод|время|можно на|хочу на/i.test(question);
    if (!wantsBooking) {
      this.#pushClient(
        text(
          base('agent', new Date().toISOString()),
          'Передал ваш вопрос Алисе — она ответит здесь. Если хотите записаться, напишите, на какую услугу и когда удобно.',
        ),
      );
      return;
    }
    const service =
      this.page.services.find((s) =>
        question.toLowerCase().includes(s.title.toLowerCase().split(' ').slice(-1)[0]!),
      ) ?? SERVICES.backMassage;
    this.#offerSlots(service);
  }

  /** Окна на ближайший день с окнами (как администратор записи на бэкенде). */
  #offerSlots(service: Service): void {
    const slots = this.listSlots(DEMO_SLUG, { service: service.id, limit: 30 });
    const firstDate = slots[0]?.start.slice(0, 10);
    const sameDay = slots.filter((s) => s.start.startsWith(firstDate ?? '')).slice(0, 4);
    if (sameDay.length === 0 || firstDate === undefined) {
      this.#pushClient(
        text(
          base('agent', new Date().toISOString()),
          'Свободных окон в ближайшие две недели нет — передам Алисе, она предложит время.',
        ),
      );
      return;
    }
    this.#pushClient(
      slotOffer(
        base('agent', new Date().toISOString()),
        `${capitalize(onDate(firstDate))} на «${service.title.toLowerCase()}» (${service.duration_min} мин) свободно:`,
        sameDay,
      ),
    );
  }

  #ensureClientConversation(id: string): void {
    if (id !== CLIENT_CONVERSATION_ID)
      throw new MockProblem(404, 'conversation_not_found', 'Переписка не найдена');
  }

  #pushClient(message: Message): void {
    this.#clientMessages = [...this.#clientMessages, message];
    this.clientLog.publish('message.created', { type: 'message.created', message });
  }

  #replaceClient(message: Message): void {
    this.#clientMessages = this.#clientMessages.map((m) => (m.id === message.id ? message : m));
    this.clientLog.publish('message.updated', { type: 'message.updated', message });
  }

  #updateClientAppointment(appointment: Appointment): void {
    this.#clientAppointments.set(appointment.id, appointment);
    for (const m of this.#clientMessages) {
      if (m.kind === 'booking_card' && m.appointment.id === appointment.id) {
        this.#replaceClient({ ...m, appointment });
      }
    }
  }

  /** Загруженное голосовое — `blob:` URL (проигрывается без сети). */
  #storeUpload(blob: Blob): string {
    const url = URL.createObjectURL(blob);
    this.#uploads.set(url, blob);
    return url;
  }

  // ─────────────────────────── график мастера ───────────────────────────

  daySchedule(date: string): DaySchedule {
    const monday = addDays(date, -weekday(date));
    const week = Array.from({ length: 7 }, (_, i) => {
      const d = addDays(monday, i);
      return { date: d, day_off: this.settings.isDayOff(d) };
    });
    if (this.settings.isDayOff(date)) {
      return {
        date,
        week,
        day_off: true,
        items: [],
        summary: { appointments: 0, pending_requests: 0, free_minutes: 0 },
      };
    }

    const busy: ScheduleItem[] = [
      ...[...this.#appointments.values()]
        .filter((a) => a.start.startsWith(date) && a.status !== 'cancelled')
        .map((a): ScheduleItem => ({
          kind: 'appointment',
          appointment: a,
          conversation_id: this.#conversationOf(a.client.id),
        })),
      ...this.#breaks
        .filter((b) => b.date === date)
        .map((b): ScheduleItem => ({
          kind: 'break',
          start: at(date, b.start),
          end: at(date, b.end),
          title: b.title,
        })),
    ].sort((a, b) => Date.parse(startOf(a)) - Date.parse(startOf(b)));

    const items: ScheduleItem[] = [];
    const hours = this.settings.hoursOn(date);
    let cursor = at(date, hours[0]?.start ?? '10:00');
    for (const item of busy) {
      if (Date.parse(startOf(item)) > Date.parse(cursor))
        items.push({ kind: 'free', start: cursor, end: startOf(item) });
      items.push(item);
      if (Date.parse(endOf(item)) > Date.parse(cursor)) cursor = endOf(item);
    }
    const close = at(date, hours.at(-1)?.end ?? '19:00');
    if (Date.parse(close) > Date.parse(cursor))
      items.push({ kind: 'free', start: cursor, end: close });

    const appointments = busy.filter(
      (i): i is Extract<ScheduleItem, { kind: 'appointment' }> => i.kind === 'appointment',
    );
    return {
      date,
      week,
      day_off: false,
      items,
      summary: {
        appointments: appointments.length,
        pending_requests: appointments.filter((i) => i.appointment.status === 'requested').length,
        free_minutes: items
          .filter((i) => i.kind === 'free')
          .reduce((sum, i) => sum + minutesBetween(startOf(i), endOf(i)), 0),
      },
    };
  }

  confirmAppointment(id: string): Appointment {
    const current = this.#requested(id);
    const confirmed: Appointment = {
      ...stripStatus(current),
      status: 'confirmed',
      confirmed_at: new Date().toISOString(),
      reminder: 'none',
    };
    this.#updateMasterAppointment(confirmed, 'Запись подтверждена');
    return confirmed;
  }

  declineAppointment(id: string, offerAlternatives: boolean): Appointment {
    const current = this.#requested(id);
    const declined: Appointment = {
      ...stripStatus(current),
      status: 'cancelled',
      cancelled_by: 'master',
    };
    this.#updateMasterAppointment(
      declined,
      offerAlternatives ? 'Агент предложит другое время' : 'Заявка отклонена',
    );
    const conversationId = this.#conversationOf(current.client.id);
    if (offerAlternatives && conversationId) {
      this.#later(() =>
        this.#pushDialog(
          conversationId,
          text(
            base('agent', new Date().toISOString()),
            'Алиса не сможет в это время. Могу предложить другие окна — какой день удобен?',
          ),
        ),
      );
    }
    return declined;
  }

  #requested(id: string): Appointment {
    const current = this.#appointments.get(id);
    if (!current) throw new MockProblem(404, 'appointment_not_found', 'Запись не найдена');
    if (current.status !== 'requested')
      throw new MockProblem(409, 'appointment_not_requested', 'Заявка уже обработана');
    return current;
  }

  #updateMasterAppointment(appointment: Appointment, preview: string): void {
    this.#appointments.set(appointment.id, appointment);
    this.masterLog.publish('appointment.updated', { type: 'appointment.updated', appointment });
    const conversationId = this.#conversationOf(appointment.client.id);
    if (!conversationId) return;
    const dialog = this.#dialogs.get(conversationId) ?? [];
    for (const m of dialog) {
      if (m.kind === 'booking_card' && m.appointment.id === appointment.id) {
        this.#replaceDialog(conversationId, { ...m, appointment });
      }
    }
    this.#patchConversation(conversationId, {
      needs_me: null,
      last_message: { author: 'master', preview, created_at: new Date().toISOString() },
    });
  }

  #conversationOf(clientId: string): string | null {
    for (const c of this.#inbox.values()) if (c.client.id === clientId) return c.id;
    return null;
  }

  // ─────────────────────────── чаты мастера ───────────────────────────

  inbox(
    filter: ConversationFilter,
    q: string | null,
  ): { items: ConversationSummary[]; counts: Record<ConversationFilter, number> } {
    const all = [...this.#inbox.values()].sort(
      (a, b) =>
        Number(b.needs_me !== null) - Number(a.needs_me !== null) ||
        Date.parse(b.last_message?.created_at ?? '0') -
          Date.parse(a.last_message?.created_at ?? '0'),
    );
    const matches = (c: ConversationSummary, f: ConversationFilter): boolean =>
      f === 'all' ||
      (f === 'needs_me' && c.needs_me !== null) ||
      (f === 'agent' && c.handler === 'agent') ||
      (f === 'me' && c.handler === 'master');
    const needle = q?.trim().toLowerCase() ?? '';
    const found = (c: ConversationSummary): boolean =>
      needle === '' ||
      c.client.display_name.toLowerCase().includes(needle) ||
      (c.client.phone_masked ?? '')
        .replace(/\D/g, '')
        .includes(needle.replace(/\D/g, '') || '\u0000') ||
      (this.#dialogs.get(c.id) ?? []).some(
        (m) => 'text' in m && m.text.toLowerCase().includes(needle),
      );
    return {
      items: all.filter((c) => matches(c, filter) && found(c)),
      counts: {
        all: all.length,
        needs_me: all.filter((c) => matches(c, 'needs_me')).length,
        agent: all.filter((c) => matches(c, 'agent')).length,
        me: all.filter((c) => matches(c, 'me')).length,
      },
    };
  }

  conversation(id: string): ConversationSummary {
    const found = this.#inbox.get(id);
    if (!found) throw new MockProblem(404, 'conversation_not_found', 'Переписка не найдена');
    return found;
  }

  dialogMessages(id: string, before: string | null, limit: number): MessagePage {
    this.conversation(id);
    this.#patchConversation(id, { unread: 0 });
    return page(this.#dialogs.get(id) ?? [], before, limit);
  }

  sendMasterMessage(
    id: string,
    clientId: string,
    body: string,
  ): { message: Message; handler: Handler } {
    this.conversation(id);
    const existing = (this.#dialogs.get(id) ?? []).find((m) => m.client_id === clientId);
    if (existing) return { message: existing, handler: 'master' };
    const message = text(base('master', new Date().toISOString(), { clientId, ai: false }), body);
    this.#pushDialog(id, message);
    this.#patchConversation(id, {
      handler: 'master',
      needs_me: null,
      last_message: { author: 'master', preview: body, created_at: message.created_at },
    });
    return { message, handler: 'master' };
  }

  setHandler(id: string, handler: Handler): Handler {
    this.conversation(id);
    this.#patchConversation(id, { handler });
    return handler;
  }

  #pushDialog(conversationId: string, message: Message): void {
    this.#dialogs.set(conversationId, [...(this.#dialogs.get(conversationId) ?? []), message]);
    this.masterLog.publish('message.created', {
      type: 'message.created',
      conversation_id: conversationId,
      message,
    });
  }

  #replaceDialog(conversationId: string, message: Message): void {
    this.#dialogs.set(
      conversationId,
      (this.#dialogs.get(conversationId) ?? []).map((m) => (m.id === message.id ? message : m)),
    );
    this.masterLog.publish('message.updated', {
      type: 'message.updated',
      conversation_id: conversationId,
      message,
    });
  }

  #patchConversation(id: string, patch: Partial<ConversationSummary>): void {
    const current = this.#inbox.get(id);
    if (!current) return;
    const next = { ...current, ...patch };
    this.#inbox.set(id, next);
    this.masterLog.publish('conversation.updated', {
      type: 'conversation.updated',
      conversation: next,
    });
  }

  // ─────────────────────────── поручения ───────────────────────────

  assistantMessages(before: string | null, limit: number): MessagePage {
    return page(this.#assistant, before, limit);
  }

  sendAssistantText(clientId: string, body: string): Message {
    const existing = this.#assistant.find((m) => m.client_id === clientId);
    if (existing) return existing;
    const message = text(base('master', new Date().toISOString(), { clientId, ai: false }), body);
    this.#pushAssistant(message);
    this.#later(() => this.#assistantReply(body));
    return message;
  }

  sendAssistantVoice(clientId: string, audio: Blob, duration: number): Message {
    const existing = this.#assistant.find((m) => m.client_id === clientId);
    if (existing) return existing;
    const message = voice(
      base('master', new Date().toISOString(), { clientId, ai: false }),
      duration,
      null,
      this.#storeUpload(audio),
    );
    this.#pushAssistant(message);
    this.#later(() => {
      const transcript = 'Закрой воскресенье';
      this.#replaceAssistant({ ...message, transcript });
      this.#later(() => this.#assistantReply(transcript));
    });
    return message;
  }

  chooseOption(choiceId: string, optionId: string): Message {
    const choice = this.#assistant.find(
      (m): m is MessageOf<'choice'> => m.kind === 'choice' && m.choice_id === choiceId,
    );
    if (!choice) throw new MockProblem(404, 'choice_not_found', 'Вопрос не найден');
    if (choice.selected_option_id !== null)
      throw new MockProblem(409, 'choice_already_answered', 'Вариант уже выбран');
    const option = choice.options.find((o) => o.id === optionId);
    if (!option) throw new MockProblem(422, 'unknown_option', 'Нет такого варианта');
    const answered: Message = { ...choice, selected_option_id: optionId };
    this.#replaceAssistant(answered);
    this.#later(() => this.#runTask(option.label, option.tone === 'muted'));
    return answered;
  }

  #assistantReply(body: string): void {
    const lower = body.toLowerCase();
    const now = new Date().toISOString();
    if (lower.includes('завтра')) {
      const tomorrow = localDate(1);
      const day = this.daySchedule(tomorrow);
      const list = day.items
        .filter(
          (i): i is Extract<ScheduleItem, { kind: 'appointment' }> => i.kind === 'appointment',
        )
        .map(
          (i) =>
            `${hhmm(i.appointment.start)} — ${i.appointment.client.display_name}, ${i.appointment.service.title.toLowerCase()}`,
        );
      this.#pushAssistant(
        text(
          base('agent', now),
          list.length
            ? `Завтра, ${humanDate(tomorrow)}:\n${list.join('\n')}`
            : `Завтра, ${humanDate(tomorrow)}, записей нет.`,
        ),
      );
      return;
    }
    const sunday = addDays(localDate(0), 6 - weekday(localDate(0)));
    const question = lower.includes('воскрес')
      ? {
          text: `Закрыть воскресенье, ${humanDate(sunday)}, для записи?`,
          detail: 'Записей на этот день нет.',
          yes: 'Да, закрыть',
        }
      : lower.includes('обед')
        ? {
            text: 'Поставить обед 14:00–15:00 на сегодня?',
            detail: 'В 14:00 записана Марина С. — предложу ей 15:30.',
            yes: 'Поставить и предложить Марине 15:30',
          }
        : { text: `Правильно понял: «${body}»?`, detail: '', yes: 'Да, выполняй' };
    const choice: MessageOf<'choice'> = {
      ...base('agent', now),
      kind: 'choice',
      choice_id: uuidv7(),
      text: question.text,
      ...(question.detail && { detail: question.detail }),
      options: [
        { id: 'yes', label: question.yes },
        { id: 'no', label: 'Ничего не менять', tone: 'muted' },
      ],
      selected_option_id: null,
    };
    this.#pushAssistant(choice);
  }

  #runTask(label: string, cancelled: boolean): void {
    const now = new Date().toISOString();
    if (cancelled) {
      this.#pushAssistant(text(base('agent', now), 'Хорошо, ничего не меняю.'));
      return;
    }
    let task: MessageOf<'task_progress'> = {
      ...base('agent', now),
      kind: 'task_progress',
      task_id: uuidv7(),
      title: 'Выполняю',
      steps: [
        { id: 'plan', label: `Принял: «${label}»`, state: 'done' },
        { id: 'apply', label: 'Меняю график', state: 'waiting' },
        { id: 'notify', label: 'Сообщаю клиентам, кого это касается', state: 'pending' },
      ],
      footnote: 'Если что-то пойдёт не так — ничего не меняю и пишу вам.',
    };
    this.#pushAssistant(task);
    const advance = (): void => {
      const index = task.steps.findIndex((s) => s.state !== 'done');
      if (index === -1) return;
      const steps = task.steps.map((s, i) =>
        i === index
          ? { ...s, state: 'done' as const }
          : i === index + 1
            ? { ...s, state: 'waiting' as const }
            : s,
      );
      const done = steps.every((s) => s.state === 'done');
      task = { ...task, steps, ...(done && { title: 'Готово', footnote: 'Всё сделал.' }) };
      this.#replaceAssistant(task);
      if (!done) this.#later(advance, this.#opts.taskStepMs);
    };
    this.#later(advance, this.#opts.taskStepMs);
  }

  #pushAssistant(message: Message): void {
    this.#assistant = [...this.#assistant, message];
    this.masterLog.publish('message.created', {
      type: 'message.created',
      conversation_id: null,
      message,
    });
  }

  #replaceAssistant(message: Message): void {
    this.#assistant = this.#assistant.map((m) => (m.id === message.id ? message : m));
    this.masterLog.publish('message.updated', {
      type: 'message.updated',
      conversation_id: null,
      message,
    });
  }

  #later(run: () => void, ms: number = this.#opts.agentDelayMs): void {
    const timer = setTimeout(() => {
      this.#timers.delete(timer);
      run();
    }, ms);
    this.#timers.add(timer);
  }
}

/** Страница истории: до `before` (не включая), последние `limit`. */
function page(all: Message[], before: string | null, limit: number): MessagePage {
  const end = before ? all.findIndex((m) => m.id === before) : all.length;
  const stop = end === -1 ? all.length : end;
  const start = Math.max(0, stop - limit);
  return { items: all.slice(start, stop), has_more: start > 0 };
}

function startOf(item: ScheduleItem): string {
  return item.kind === 'appointment' ? item.appointment.start : item.start;
}

function endOf(item: ScheduleItem): string {
  return item.kind === 'appointment' ? item.appointment.end : item.end;
}

/** Поля записи без полей, зависящих от статуса. */
function stripStatus(
  a: Appointment,
): Pick<Appointment, 'id' | 'service' | 'start' | 'end' | 'client' | 'note'> {
  return {
    id: a.id,
    service: a.service,
    start: a.start,
    end: a.end,
    client: a.client,
    ...(a.note !== undefined && { note: a.note }),
  };
}
