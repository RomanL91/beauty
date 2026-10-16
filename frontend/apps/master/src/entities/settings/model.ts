import { ApiError, type Money, type TimeInterval, type WorkingDay } from '@beauty/api';

/** Ключ запроса настроек. */
export const settingsKey = ['settings'] as const;

/** Дни недели: 0 — понедельник (как в контракте). */
export const WEEKDAYS = [
  { day: 0, short: 'Пн', long: 'Понедельник' },
  { day: 1, short: 'Вт', long: 'Вторник' },
  { day: 2, short: 'Ср', long: 'Среда' },
  { day: 3, short: 'Чт', long: 'Четверг' },
  { day: 4, short: 'Пт', long: 'Пятница' },
  { day: 5, short: 'Сб', long: 'Суббота' },
  { day: 6, short: 'Вс', long: 'Воскресенье' },
] as const;

/** Часовые пояса Казахстана и соседей (значение — IANA). */
export const TIMEZONES = [
  { id: 'Asia/Almaty', label: 'Астана, Алматы (UTC+5)' },
  { id: 'Asia/Aqtobe', label: 'Актобе (UTC+5)' },
  { id: 'Asia/Oral', label: 'Уральск (UTC+5)' },
  { id: 'Europe/Moscow', label: 'Москва (UTC+3)' },
] as const;

/** Шаги сетки окон, минуты (как в контракте). */
export const SLOT_STEPS = [5, 10, 15, 20, 30, 60] as const;

// ───────────────────────────── цены ─────────────────────────────

/** Сумма в тиынах → строка в тенге для поля ввода («12000», «9500,50»). */
export function tengeText(price: Money | null): string {
  if (!price) return '';
  const tenge = Math.floor(price.amount / 100);
  const tiyn = price.amount % 100;
  return tiyn === 0 ? String(tenge) : `${tenge},${String(tiyn).padStart(2, '0')}`;
}

/**
 * Строка в тенге → цена в тиынах. Пусто — «цена по запросу» (`null`); пробелы-разделители
 * разрядов и запятая допустимы. Неверное значение — `undefined`.
 */
export function parseTenge(text: string): Money | null | undefined {
  const cleaned = text.replace(/[\s₸]/g, '').replace(',', '.');
  if (cleaned === '') return null;
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(cleaned)) return undefined;
  const [whole = '0', fraction = ''] = cleaned.split('.');
  return { amount: Number(whole) * 100 + Number(fraction.padEnd(2, '0')), currency: 'KZT' };
}

// ───────────────────────────── график ─────────────────────────────

const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** «HH:MM» → минуты от полуночи (неверное — `null`). */
export function toMinutes(hm: string): number | null {
  const match = HHMM.exec(hm);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

/** Ошибка интервалов одного дня (или `null`, если всё верно). */
export function intervalsError(intervals: readonly TimeInterval[]): string | null {
  const parsed = intervals.map((i) => ({ start: toMinutes(i.start), end: toMinutes(i.end) }));
  if (parsed.some((i) => i.start === null || i.end === null)) return 'Время — в формате ЧЧ:ММ';
  const sorted = (parsed as Array<{ start: number; end: number }>).sort(
    (a, b) => a.start - b.start,
  );
  if (sorted.some((i) => i.start % 5 !== 0 || i.end % 5 !== 0)) return 'Минуты — кратные 5';
  if (sorted.some((i) => i.start >= i.end)) return 'Начало должно быть раньше конца';
  for (let k = 1; k < sorted.length; k += 1) {
    if (sorted[k]!.start < sorted[k - 1]!.end) return 'Интервалы пересекаются';
  }
  return null;
}

/** Черновик недели: семь дней, у выходного — пустой список интервалов. */
export type WeekDraft = TimeInterval[][];

/** Неделя из настроек → черновик на 7 дней. */
export function weekDraft(days: readonly WorkingDay[]): WeekDraft {
  return WEEKDAYS.map(({ day }) =>
    (days.find((d) => d.weekday === day)?.intervals ?? []).map((i) => ({ ...i })),
  );
}

/** Черновик → тело запроса (только рабочие дни, интервалы по порядку). */
export function workingDays(draft: WeekDraft): WorkingDay[] {
  return draft.flatMap((intervals, weekday) =>
    intervals.length === 0
      ? []
      : [
          {
            weekday,
            intervals: [...intervals].sort(
              (a, b) => (toMinutes(a.start) ?? 0) - (toMinutes(b.start) ?? 0),
            ),
          },
        ],
  );
}

/** Ошибки черновика по дням (индекс — день недели). */
export function weekErrors(draft: WeekDraft): Array<string | null> {
  return draft.map((intervals) => intervalsError(intervals));
}

/** «10:00–14:00, 15:00–19:00» или «выходной». */
export function intervalsText(intervals: readonly TimeInterval[]): string {
  return intervals.length === 0
    ? 'выходной'
    : intervals.map((i) => `${i.start}–${i.end}`).join(', ');
}

// ───────────────────────────── прочее ─────────────────────────────

/**
 * Адрес страницы мастера: кабинет открыт на `master.<домен>`, страница — на
 * `<slug>.<домен>` (тот же порт и схема). Иначе — `https://<slug>.beautiful.kz`.
 */
export function pageUrl(slug: string, location: { protocol: string; host: string }): string {
  const { protocol, host } = location;
  if (host.startsWith('master.')) return `${protocol}//${slug}.${host.slice('master.'.length)}/`;
  return `https://${slug}.beautiful.kz/`;
}

/** Текст ошибки сохранения для пользователя. */
export function saveErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не получилось сохранить — попробуйте ещё раз';
  if (error.isNetwork) return 'Нет соединения — изменения не сохранены';
  if (error.code === 'validation_error') return 'Проверьте поля формы';
  if (error.status === 413) return 'Фото больше 8 МБ';
  if (error.status >= 500) return 'Сервер не ответил — попробуйте ещё раз';
  return error.message || 'Не получилось сохранить';
}
