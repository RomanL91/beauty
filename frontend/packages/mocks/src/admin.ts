import type {
  AdminAccount,
  AdminAgentReport,
  AdminAuditEntry,
  AdminClientRow,
  AdminDashboard,
  AdminMasterDetail,
  AdminMasterInput,
  AdminMasterRow,
  AdminSession,
  AdminSystem,
  MasterPage,
  MasterStatus,
} from '@beauty/api';
import { addDays, localDate, fromNow } from './clock';
import type { KeyValueStore } from './db';
import { MockProblem } from './errors';
import { DEMO_SLUG } from './fixtures/master-page';
import { uuidv7 } from './ids';
import type { MockSettings } from './settings';

/** Вход в мок-панель (e2e, разработка). */
export const MOCK_ADMIN_LOGIN = 'owner';
export const MOCK_ADMIN_PASSWORD = 'beauty-admin-2026';

const SESSION_KEY = 'beauty-mock-admin';
const CSRF = 'mock-csrf-token';
const ALISA_ID = '0192a0c0-0000-7000-8000-000000000301';
const MIN_PASSWORD = 10;

interface MockMaster {
  row: AdminMasterRow;
  page: MasterPage;
  publishedAt: string | null;
  blockers: string[];
}

interface MockAdminAccount extends AdminAccount {
  password: string;
}

/** Синтетический ряд: правдоподобные числа без случайности (скриншоты одинаковые). */
const wave = (day: number, base: number, amplitude: number) =>
  Math.max(0, Math.round(base + amplitude * Math.sin(day / 2.3) + (day % 5) - 2));

/**
 * Админ-панель в моках: администраторы, сессия (флаг в хранилище «cookie»), мастера
 * (Алиса — та же страница, что у кабинета и клиента), клиенты, отчёты, журнал.
 */
export class MockAdmin {
  readonly #admins: MockAdminAccount[];
  readonly #masters = new Map<string, MockMaster>();
  readonly #clients: AdminClientRow[];
  readonly #audit: AdminAuditEntry[] = [];

  constructor(
    private readonly page: MasterPage,
    private readonly settings: MockSettings,
    private readonly storage: KeyValueStore,
  ) {
    const created = fromNow(-120 * 86_400_000);
    this.#admins = [
      {
        id: '0192a0c0-0000-7000-8000-000000000901',
        login: MOCK_ADMIN_LOGIN,
        display_name: 'Хозяин сервиса',
        active: true,
        created_at: created,
        last_login_at: fromNow(-3_600_000),
        password: MOCK_ADMIN_PASSWORD,
      },
      {
        id: '0192a0c0-0000-7000-8000-000000000902',
        login: 'support',
        display_name: 'Поддержка',
        active: true,
        created_at: fromNow(-30 * 86_400_000),
        last_login_at: fromNow(-2 * 86_400_000),
        password: 'support-password',
      },
    ];
    this.#seedMasters();
    const phones = ['+77059998967', '+77011231234', '+77074564510', '+77027897721', '+77053213008'];
    this.#clients = phones.map((phone, i) => ({
      id: `0192a0c0-0000-7000-8000-00000000080${i}`,
      phone,
      created_at: fromNow(-(40 - i * 7) * 86_400_000),
      last_login_at: fromNow(-(i + 1) * 3_600_000 * 5),
      masters: i === 4 ? [DEMO_SLUG, 'kamila'] : [DEMO_SLUG],
      appointments: 6 - i,
      blocked: false,
      blocked_reason: null,
    }));
    this.#log('master.created', 'dana', 'Завёл мастера Дана Ахметова, владелец +77010007788', 5);
    this.#log('agent.disabled', 'kamila', 'Выключил ИИ-администратора', 3);
    this.#log('master.published', DEMO_SLUG, 'Опубликовал страницу', 1);
  }

  // ─────────────────────────── вход ───────────────────────────

  login(login: string, password: string): AdminSession {
    const admin = this.#admins.find((a) => a.login === login.trim().toLowerCase() && a.active);
    if (!admin || admin.password !== password)
      throw new MockProblem(401, 'invalid_credentials', 'Неверный логин или пароль');
    admin.last_login_at = new Date().toISOString();
    this.storage.set(SESSION_KEY, admin.id);
    return this.#session(admin);
  }

  me(): AdminSession {
    return this.#session(this.#current());
  }

  /** Проверка сессии и CSRF (изменяющие запросы). */
  authorize(csrf: string | null, change: boolean): AdminAccount {
    const admin = this.#current();
    if (change && csrf !== CSRF) throw new MockProblem(403, 'csrf_failed', 'Нет CSRF-токена');
    return admin;
  }

  logout(): void {
    this.storage.remove(SESSION_KEY);
  }

  changePassword(current: string, next: string): void {
    const admin = this.#current();
    if (admin.password !== current)
      throw new MockProblem(403, 'wrong_password', 'Текущий пароль неверен');
    this.#strong(next);
    admin.password = next;
    this.#log('admin.password_changed', admin.login, 'Сменил свой пароль');
  }

  // ─────────────────────────── отчёты ───────────────────────────

  dashboard(): AdminDashboard {
    const masters = this.masters();
    return {
      totals: {
        masters: masters.length,
        published: masters.filter((m) => m.status === 'published').length,
        agents_enabled: masters.filter((m) => m.agent === 'enabled').length,
        clients: this.#clients.length + 137,
        blocked_clients: this.#clients.filter((c) => c.blocked).length,
        upcoming_appointments: 23,
        pending_requests: 2,
        conversations: 164,
      },
      days: Array.from({ length: 30 }, (_, i) => ({
        date: localDate(i - 29),
        requested: wave(i, 6, 3),
        confirmed: wave(i + 1, 5, 2),
        cancelled: wave(i + 3, 1, 1),
        new_clients: wave(i + 2, 4, 2),
        messages: wave(i, 38, 14),
        agent_turns: wave(i, 30, 10),
        agent_failures: i % 9 === 0 ? 1 : 0,
      })),
    };
  }

  masters(query?: string | null, status?: string | null): AdminMasterRow[] {
    const q = (query ?? '').trim().toLowerCase();
    const digits = q.replace(/\D/g, '');
    return [...this.#masters.values()]
      .map((m) => this.#fresh(m).row)
      .filter((m) => !status || m.status === status)
      .filter(
        (m) =>
          !q ||
          m.slug.includes(q) ||
          m.display_name.toLowerCase().includes(q) ||
          (digits !== '' && (m.owner_phone ?? '').includes(digits)),
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }

  master(id: string): AdminMasterDetail {
    const master = this.#masters.get(id);
    if (!master) throw new MockProblem(404, 'master_not_found', 'Мастер не найден');
    const { row, page, publishedAt, blockers } = this.#fresh(master);
    const today = localDate();
    return {
      ...row,
      page,
      published_at: publishedAt,
      publish_blockers: blockers,
      agent_command:
        row.agent === 'not_connected'
          ? `docker compose run --rm agent-setup "beauty agent provision ${row.slug}"`
          : null,
      stats: {
        clients: row.slug === DEMO_SLUG ? 42 : 0,
        conversations: row.slug === DEMO_SLUG ? 48 : 0,
        requested: row.appointments_30d,
        confirmed: Math.round(row.appointments_30d * 0.8),
        cancelled: Math.round(row.appointments_30d * 0.1),
        completed: Math.round(row.appointments_30d * 0.6),
        agent_turns: row.agent === 'not_connected' ? 0 : row.appointments_30d * 6,
        agent_failures: row.agent === 'not_connected' ? 0 : 2,
        handoffs: row.agent === 'not_connected' ? 0 : 5,
      },
      upcoming:
        row.slug === DEMO_SLUG
          ? [
              {
                id: uuidv7(),
                start: `${addDays(today, 1)}T12:00:00+05:00`,
                status: 'requested',
                service: 'Классический массаж спины',
                client: '+77059998967',
              },
              {
                id: uuidv7(),
                start: `${addDays(today, 2)}T15:30:00+05:00`,
                status: 'confirmed',
                service: 'Чистка лица комбинированная',
                client: '+77074564510',
              },
            ]
          : [],
    };
  }

  clients(query: string | null, blocked: boolean | null, limit: number, offset: number) {
    const digits = (query ?? '').replace(/\D/g, '');
    const found = this.#clients.filter(
      (c) => (!digits || c.phone.includes(digits)) && (blocked === null || c.blocked === blocked),
    );
    return { items: found.slice(offset, offset + limit), total: found.length };
  }

  agent(): AdminAgentReport {
    return {
      runtime: 'hermes',
      model: 'google/gemini-2.5-flash',
      speech: { provider: 'openrouter', model: 'openai/whisper-large-v3' },
      days: Array.from({ length: 14 }, (_, i) => ({
        date: localDate(i - 13),
        front_desk: wave(i, 24, 8),
        office: wave(i + 4, 5, 3),
        failures: i % 6 === 0 ? 1 : 0,
        handoffs: wave(i, 3, 2),
        avg_seconds: 2.4 + (i % 4) * 0.3,
        p95_seconds: 5.1 + (i % 3) * 0.8,
      })),
      failures: [
        {
          at: fromNow(-26 * 3_600_000),
          master: DEMO_SLUG,
          face: 'front_desk',
          status: 'timeout',
          seconds: 120,
        },
        {
          at: fromNow(-80 * 3_600_000),
          master: 'kamila',
          face: 'back_office',
          status: 'no_reply',
          seconds: 3.2,
        },
      ],
      voice: { total: 31, transcribed: 29 },
    };
  }

  system(): AdminSystem {
    return {
      environment: 'dev',
      database: true,
      outbox: { pending: 0, oldest_seconds: null },
      jobs: { scheduled: 12, overdue: 0 },
      features: { agent: true, speech: true, push: false },
    };
  }

  admins(): AdminAccount[] {
    return this.#admins.map(({ password: _password, ...admin }) => admin);
  }

  audit(before: string | null, limit: number) {
    const start = before ? this.#audit.findIndex((e) => e.id === before) + 1 : 0;
    const items = this.#audit.slice(start, start + limit);
    return { items, has_more: start + limit < this.#audit.length };
  }

  // ─────────────────────────── действия ───────────────────────────

  createMaster(input: AdminMasterInput): AdminMasterDetail {
    const slug = input.slug.trim().toLowerCase();
    if (!/^[a-z0-9-]{2,40}$/.test(slug))
      throw new MockProblem(422, 'invalid_slug', 'Адрес — латиница, цифры и дефис, 2–40 символов');
    if ([...this.#masters.values()].some((m) => m.row.slug === slug))
      throw new MockProblem(409, 'slug_taken', 'Этот адрес уже занят');
    const owner = this.#phone(input.owner_phone ?? null);
    const id = uuidv7();
    const now = new Date().toISOString();
    this.#masters.set(id, {
      row: {
        id,
        slug,
        display_name: input.display_name.trim(),
        specialty: (input.specialty ?? '').trim(),
        status: 'draft',
        owner_phone: owner,
        agent: 'not_connected',
        services: 0,
        appointments_30d: 0,
        created_at: now,
        last_activity_at: null,
      },
      page: {
        slug,
        display_name: input.display_name.trim(),
        name_forms: input.name_forms,
        specialty: (input.specialty ?? '').trim(),
        address: '',
        timezone: input.timezone,
        avatar_url: null,
        about: '',
        services: [],
        photos: [],
        booking_rules: { confirm_within_hours: 2, change_deadline_hours: 12 },
      },
      publishedAt: null,
      blockers: ['Добавьте хотя бы одну услугу', 'Задайте рабочие часы'],
    });
    const suffix = owner ? `, владелец ${owner}` : '';
    this.#log('master.created', slug, `Завёл мастера ${input.display_name.trim()}${suffix}`);
    return this.master(id);
  }

  setOwner(id: string, phone: string): AdminMasterDetail {
    const master = this.#require(id);
    const owner = this.#phone(phone);
    const before = master.row.owner_phone;
    master.row.owner_phone = owner;
    this.#log('master.owner_changed', master.row.slug, `Владелец: ${before ?? '—'} → ${owner}`);
    return this.master(id);
  }

  setPublication(id: string, published: boolean): AdminMasterDetail {
    const master = this.#fresh(this.#require(id));
    if (master.row.slug === DEMO_SLUG) {
      if (published) this.settings.publish();
      else this.settings.unpublish();
    } else if (published && master.blockers.length > 0) {
      throw new MockProblem(409, 'master_not_publishable', master.blockers.join('. '));
    } else {
      master.row.status = published ? 'published' : 'draft';
      master.publishedAt = published ? new Date().toISOString() : master.publishedAt;
    }
    this.#log(
      published ? 'master.published' : 'master.unpublished',
      master.row.slug,
      published ? 'Опубликовал страницу' : 'Скрыл страницу',
    );
    return this.master(id);
  }

  setAgent(id: string, enabled: boolean): AdminMasterDetail {
    const master = this.#require(id);
    if (master.row.agent === 'not_connected')
      throw new MockProblem(404, 'agent_not_provisioned', 'ИИ-администратор мастеру не подключён');
    master.row.agent = enabled ? 'enabled' : 'disabled';
    this.#log(
      enabled ? 'agent.enabled' : 'agent.disabled',
      master.row.slug,
      enabled ? 'Включил ИИ-администратора' : 'Выключил ИИ-администратора',
    );
    return this.master(id);
  }

  setClientBlock(id: string, blocked: boolean, reason?: string | null): AdminClientRow {
    const client = this.#clients.find((c) => c.id === id);
    if (!client) throw new MockProblem(404, 'account_not_found', 'Клиент не найден');
    client.blocked = blocked;
    client.blocked_reason = blocked ? reason?.trim() || null : null;
    this.#log(
      blocked ? 'client.blocked' : 'client.unblocked',
      client.phone,
      blocked
        ? `Заблокировал клиента${client.blocked_reason ? `: ${client.blocked_reason}` : ''}`
        : 'Разблокировал клиента',
    );
    return client;
  }

  createAdmin(input: { login: string; display_name: string; password: string }): AdminAccount {
    const login = input.login.trim().toLowerCase();
    if (!/^[a-z0-9._-]{3,64}$/.test(login))
      throw new MockProblem(
        422,
        'invalid_admin_login',
        'Логин — латиница, цифры, . _ -, 3–64 символа',
      );
    if (this.#admins.some((a) => a.login === login))
      throw new MockProblem(409, 'admin_login_taken', `Логин ${login} занят`);
    this.#strong(input.password);
    const admin: MockAdminAccount = {
      id: uuidv7(),
      login,
      display_name: input.display_name.trim(),
      active: true,
      created_at: new Date().toISOString(),
      last_login_at: null,
      password: input.password,
    };
    this.#admins.push(admin);
    this.#log('admin.created', login, `Добавил администратора ${admin.display_name}`);
    const { password: _password, ...view } = admin;
    return view;
  }

  updateAdmin(id: string, patch: { active?: boolean; password?: string }): AdminAccount {
    const admin = this.#admins.find((a) => a.id === id);
    if (!admin) throw new MockProblem(404, 'admin_not_found', 'Администратор не найден');
    if (patch.active === false && admin.id === this.#current().id)
      throw new MockProblem(409, 'cannot_disable_self', 'Себя отключить нельзя');
    const changes: string[] = [];
    if (patch.active !== undefined && patch.active !== admin.active) {
      admin.active = patch.active;
      changes.push(patch.active ? 'включил' : 'отключил');
    }
    if (patch.password !== undefined) {
      this.#strong(patch.password);
      admin.password = patch.password;
      changes.push('задал пароль');
    }
    if (changes.length)
      this.#log(
        'admin.updated',
        admin.login,
        `Администратор ${admin.login}: ${changes.join(', ')}`,
      );
    const { password: _password, ...view } = admin;
    return view;
  }

  // ─────────────────────────── внутреннее ───────────────────────────

  #current(): MockAdminAccount {
    const id = this.storage.get(SESSION_KEY);
    const admin = this.#admins.find((a) => a.id === id && a.active);
    if (!admin) throw new MockProblem(401, 'admin_unauthorized', 'Войдите в панель');
    return admin;
  }

  #session(admin: MockAdminAccount): AdminSession {
    const { password: _password, ...view } = admin;
    return { admin: view, csrf_token: CSRF, expires_at: fromNow(12 * 3_600_000) };
  }

  #require(id: string): MockMaster {
    const master = this.#masters.get(id);
    if (!master) throw new MockProblem(404, 'master_not_found', 'Мастер не найден');
    return master;
  }

  /** Алиса — живая страница моков (кабинет и клиент видят те же правки). */
  #fresh(master: MockMaster): MockMaster {
    if (master.row.slug !== DEMO_SLUG) return master;
    const view = this.settings.view();
    master.row.status = view.status;
    master.row.services = view.page.services.length;
    master.row.display_name = view.page.display_name;
    master.row.specialty = view.page.specialty;
    master.page = view.page;
    master.publishedAt = view.published_at;
    master.blockers = view.publish_blockers;
    return master;
  }

  #phone(phone: string | null): string | null {
    if (phone === null || phone.trim() === '') return null;
    const cleaned = phone.replace(/[\s()-]/g, '');
    if (!/^\+7\d{10}$/.test(cleaned))
      throw new MockProblem(422, 'invalid_phone', 'Телефон в формате +7XXXXXXXXXX');
    return cleaned;
  }

  #strong(password: string): void {
    if (password.length < MIN_PASSWORD || !password.trim())
      throw new MockProblem(422, 'weak_password', `Пароль — от ${MIN_PASSWORD} символов`);
  }

  #log(action: string, target: string | null, summary: string, daysAgo = 0): void {
    const admin = this.#admins[0]!;
    this.#audit.unshift({
      id: uuidv7(),
      at: fromNow(-daysAgo * 86_400_000 - this.#audit.length * 60_000),
      admin: daysAgo ? admin.login : (this.#currentOrNull()?.login ?? admin.login),
      action,
      target,
      summary,
    });
  }

  #currentOrNull(): MockAdminAccount | null {
    const id = this.storage.get(SESSION_KEY);
    return this.#admins.find((a) => a.id === id) ?? null;
  }

  #seedMasters(): void {
    const status: MasterStatus = 'published';
    this.#masters.set(ALISA_ID, {
      row: {
        id: ALISA_ID,
        slug: DEMO_SLUG,
        display_name: this.page.display_name,
        specialty: this.page.specialty,
        status,
        owner_phone: '+77051234567',
        agent: 'enabled',
        services: this.page.services.length,
        appointments_30d: 34,
        created_at: fromNow(-90 * 86_400_000),
        last_activity_at: fromNow(-12 * 60_000),
      },
      page: this.page,
      publishedAt: fromNow(-90 * 86_400_000),
      blockers: [],
    });
    const other = (
      id: string,
      slug: string,
      name: string,
      specialty: string,
      extra: Partial<AdminMasterRow>,
    ): void => {
      const forms = { nominative: name.split(' ')[0]!, genitive: name, dative: name };
      this.#masters.set(id, {
        row: {
          id,
          slug,
          display_name: name,
          specialty,
          status: 'published',
          owner_phone: null,
          agent: 'not_connected',
          services: 3,
          appointments_30d: 0,
          created_at: fromNow(-30 * 86_400_000),
          last_activity_at: null,
          ...extra,
        },
        page: {
          slug,
          display_name: name,
          name_forms: forms,
          specialty,
          address: 'Астана',
          timezone: 'Asia/Almaty',
          avatar_url: null,
          about: '',
          services: [],
          photos: [],
          booking_rules: { confirm_within_hours: 2, change_deadline_hours: 12 },
        },
        publishedAt: extra.status === 'draft' ? null : fromNow(-20 * 86_400_000),
        blockers:
          extra.status === 'draft' ? ['Добавьте хотя бы одну услугу', 'Задайте рабочие часы'] : [],
      });
    };
    other('0192a0c0-0000-7000-8000-000000000302', 'kamila', 'Камила Сейтова', 'Брови и ресницы', {
      owner_phone: '+77012223344',
      agent: 'disabled',
      appointments_30d: 12,
      created_at: fromNow(-45 * 86_400_000),
      last_activity_at: fromNow(-26 * 3_600_000),
    });
    other('0192a0c0-0000-7000-8000-000000000303', 'dana', 'Дана Ахметова', 'Маникюр', {
      status: 'draft',
      services: 0,
      owner_phone: '+77010007788',
      created_at: fromNow(-5 * 86_400_000),
    });
  }
}
