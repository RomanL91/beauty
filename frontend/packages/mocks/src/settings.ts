import type {
  BookingRulesSettings,
  MasterPage,
  MasterSettings,
  ProfileInput,
  ServiceInput,
  WorkingDay,
} from '@beauty/api';
import { MASTER_TIMEZONE, localDate, weekday } from './clock';
import { MockProblem } from './errors';
import { WORKING_HOURS } from './fixtures/master-cabinet';
import { uuidv7 } from './ids';

const MAX_SERVICES = 50;
const MAX_PHOTOS = 30;
const STEPS = new Set([5, 10, 15, 20, 30, 60]);
const ZONES = new Set([MASTER_TIMEZONE, 'Asia/Aqtobe', 'Asia/Oral', 'Europe/Moscow', 'UTC']);
const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/;

const minutes = (hm: string): number => {
  const match = HHMM.exec(hm);
  if (!match) throw new MockProblem(422, 'invalid_schedule', `Время ${hm} — в формате ЧЧ:ММ`);
  return Number(match[1]) * 60 + Number(match[2]);
};

function text(value: string | null | undefined, field: string, max: number): string {
  const trimmed = (value ?? '').trim();
  if (trimmed.length > max)
    throw new MockProblem(422, 'invalid_profile', `Поле «${field}» — не длиннее ${max}`);
  return trimmed;
}

function required(value: string, field: string, max: number, code = 'invalid_profile'): string {
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > max)
    throw new MockProblem(422, code, `Поле «${field}» — от 1 до ${max} символов`);
  return trimmed;
}

function optional(value: string, field: string, max: number): string {
  const trimmed = value.trim();
  if (trimmed.length > max)
    throw new MockProblem(422, 'validation_error', `Поле «${field}» — не длиннее ${max} символов`);
  return trimmed;
}

/**
 * Настройки страницы мастера в моках: правки страницы `page` (её видят и клиентский мок,
 * и `GET /me`), рабочие часы, выходные даты, правила, публикация — с проверками, как у сервера.
 */
export class MockSettings {
  #status: MasterSettings['status'] = 'published';
  #publishedAt: string | null = new Date(Date.now() - 90 * 86_400_000).toISOString();
  #hours: WorkingDay[] = [0, 1, 2, 3, 4, 5].map((day) => ({
    weekday: day,
    intervals: [{ start: WORKING_HOURS.start, end: WORKING_HOURS.end }],
  }));
  #daysOff: string[] = [];
  #rules: BookingRulesSettings;

  constructor(
    private readonly page: MasterPage,
    private readonly store: (file: Blob) => string,
  ) {
    this.#rules = {
      ...page.booking_rules,
      min_notice_minutes: 60,
      horizon_days: 30,
      slot_step_minutes: 30,
    };
  }

  get published(): boolean {
    return this.#status === 'published';
  }

  /** Выходной: дня нет в рабочих часах или дата отмечена выходной. */
  isDayOff(date: string): boolean {
    return this.#daysOff.includes(date) || this.hoursOn(date).length === 0;
  }

  /** Рабочие интервалы даты. */
  hoursOn(date: string): WorkingDay['intervals'] {
    return this.#hours.find((d) => d.weekday === weekday(date))?.intervals ?? [];
  }

  view(): MasterSettings {
    return {
      page: this.page,
      status: this.#status,
      published_at: this.#publishedAt,
      working_hours: this.#hours,
      days_off: this.#daysOff,
      booking_rules: this.#rules,
      publish_blockers: this.#blockers(),
    };
  }

  updateProfile(input: ProfileInput): MasterSettings {
    if (!ZONES.has(input.timezone))
      throw new MockProblem(422, 'invalid_timezone', 'Неизвестный часовой пояс');
    const forms = input.name_forms;
    Object.assign(this.page, {
      display_name: required(input.display_name, 'имя на странице', 80),
      name_forms: {
        nominative: required(forms.nominative, 'имя', 40),
        genitive: required(forms.genitive, 'имя (кого?)', 40),
        dative: required(forms.dative, 'имя (кому?)', 40),
      },
      specialty: text(input.specialty, 'специализация', 120),
      address: text(input.address, 'адрес', 200),
      about: text(input.about, 'о себе', 2000),
      timezone: input.timezone,
    });
    return this.view();
  }

  addService(input: ServiceInput): MasterSettings {
    if (this.page.services.length >= MAX_SERVICES)
      throw new MockProblem(409, 'service_limit_reached', 'Слишком много услуг');
    this.page.services = [...this.page.services, { id: uuidv7(), ...this.#service(input) }];
    return this.view();
  }

  updateService(id: string, input: ServiceInput): MasterSettings {
    this.#find(id);
    this.page.services = this.page.services.map((s) =>
      s.id === id ? { id, ...this.#service(input) } : s,
    );
    return this.view();
  }

  archiveService(id: string): MasterSettings {
    this.#find(id);
    if (this.published && this.page.services.length === 1)
      throw new MockProblem(
        409,
        'master_not_publishable',
        'Последнюю услугу опубликованной страницы не убрать',
      );
    this.page.services = this.page.services.filter((s) => s.id !== id);
    return this.view();
  }

  setWorkingHours(days: WorkingDay[]): MasterSettings {
    const seen = new Set<number>();
    for (const day of days) {
      if (
        !Number.isInteger(day.weekday) ||
        day.weekday < 0 ||
        day.weekday > 6 ||
        seen.has(day.weekday)
      )
        throw new MockProblem(422, 'invalid_schedule', 'День недели — от 0 до 6, без повторов');
      seen.add(day.weekday);
      const sorted = [...day.intervals].sort((a, b) => minutes(a.start) - minutes(b.start));
      sorted.forEach((interval, i) => {
        const start = minutes(interval.start);
        const end = interval.end === '24:00' ? 1440 : minutes(interval.end);
        if (start % 5 || end % 5 || start >= end)
          throw new MockProblem(422, 'invalid_schedule', 'Интервал пустой или не кратен 5 минутам');
        const previous = sorted[i - 1];
        if (previous && start < minutes(previous.end))
          throw new MockProblem(422, 'invalid_schedule', 'Интервалы дня пересекаются');
      });
    }
    const working = days
      .filter((d) => d.intervals.length > 0)
      .sort((a, b) => a.weekday - b.weekday);
    if (this.published && working.length === 0)
      throw new MockProblem(
        409,
        'master_not_publishable',
        'У опубликованной страницы нужны рабочие часы',
      );
    this.#hours = working.map((d) => ({
      weekday: d.weekday,
      intervals: [...d.intervals].sort((a, b) => minutes(a.start) - minutes(b.start)),
    }));
    return this.view();
  }

  setDaysOff(days: string[]): MasterSettings {
    const today = localDate();
    this.#daysOff = [...new Set(days)].filter((d) => d >= today).sort();
    return this.view();
  }

  setBookingRules(rules: BookingRulesSettings): MasterSettings {
    const within = (value: number, min: number, max: number) =>
      Number.isInteger(value) && value >= min && value <= max;
    if (
      !within(rules.confirm_within_hours, 1, 72) ||
      !within(rules.change_deadline_hours, 0, 168) ||
      !within(rules.min_notice_minutes, 0, 10_080) ||
      !within(rules.horizon_days, 1, 90) ||
      !STEPS.has(rules.slot_step_minutes)
    )
      throw new MockProblem(422, 'invalid_booking_rules', 'Правила записи вне допустимых значений');
    this.#rules = { ...rules };
    this.page.booking_rules = {
      confirm_within_hours: rules.confirm_within_hours,
      change_deadline_hours: rules.change_deadline_hours,
    };
    return this.view();
  }

  addPhoto(file: Blob, alt: string): MasterSettings {
    this.#image(file);
    if (this.page.photos.length >= MAX_PHOTOS)
      throw new MockProblem(422, 'invalid_profile', `Не больше ${MAX_PHOTOS} фото`);
    const photo = { id: uuidv7(), url: this.store(file), alt: text(alt, 'подпись', 200) };
    this.page.photos = [...this.page.photos, photo];
    return this.view();
  }

  removePhoto(id: string): MasterSettings {
    if (!this.page.photos.some((p) => p.id === id))
      throw new MockProblem(404, 'photo_not_found', 'Фото не найдено');
    this.page.photos = this.page.photos.filter((p) => p.id !== id);
    return this.view();
  }

  setAvatar(file: Blob | null): MasterSettings {
    if (file) this.#image(file);
    this.page.avatar_url = file ? this.store(file) : null;
    return this.view();
  }

  publish(): MasterSettings {
    const blockers = this.#blockers();
    if (blockers.length > 0)
      throw new MockProblem(409, 'master_not_publishable', blockers.join('. '));
    if (!this.published) {
      this.#status = 'published';
      this.#publishedAt = new Date().toISOString();
    }
    return this.view();
  }

  unpublish(): MasterSettings {
    this.#status = 'draft';
    return this.view();
  }

  #blockers(): string[] {
    const blockers: string[] = [];
    if (this.page.services.length === 0) blockers.push('Добавьте хотя бы одну услугу');
    if (this.#hours.length === 0) blockers.push('Задайте рабочие часы');
    return blockers;
  }

  #find(id: string): void {
    if (!this.page.services.some((s) => s.id === id))
      throw new MockProblem(404, 'service_not_found', 'Услуга не найдена');
  }

  #service(input: ServiceInput): Omit<MasterPage['services'][number], 'id'> {
    const duration = input.duration_min;
    if (!Number.isInteger(duration) || duration < 5 || duration > 480 || duration % 5)
      throw new MockProblem(
        422,
        'invalid_service_duration',
        'Длительность — от 5 до 480 минут, кратно 5',
      );
    if (input.price && (!Number.isInteger(input.price.amount) || input.price.amount < 0))
      throw new MockProblem(422, 'invalid_money', 'Некорректная цена');
    return {
      title: required(input.title, 'название услуги', 120, 'invalid_profile'),
      description: optional(input.description ?? '', 'описание услуги', 1000),
      duration_min: duration,
      price: input.price ?? null,
    };
  }

  #image(file: Blob): void {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
      throw new MockProblem(422, 'invalid_photo', 'Нужна картинка JPEG, PNG или WebP');
    if (file.size > 8 * 1024 * 1024)
      throw new MockProblem(413, 'photo_too_large', 'Фото больше 8 МБ');
  }
}
