/**
 * Форматирование для интерфейса: время и даты — в поясе мастера
 * (`MasterPage.timezone`), чтобы клиент в другом городе видел время визита
 * так же, как мастер.
 */
const cache = new Map<string, Intl.DateTimeFormat>();

function fmt(timeZone: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${timeZone}|${JSON.stringify(options)}`;
  let f = cache.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat('ru-RU', { timeZone, ...options });
    cache.set(key, f);
  }
  return f;
}

/** `YYYY-MM-DD` момента в поясе. */
export function dateKey(iso: string | number, timeZone: string): string {
  const parts = fmt(timeZone, { year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(
    new Date(iso),
  );
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

/** «14:02». */
export function formatTime(iso: string, timeZone: string): string {
  return fmt(timeZone, { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(iso));
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** «Сегодня 18:00», «Завтра 12:00», «Пт 12:00». */
export function formatSlotShort(iso: string, timeZone: string, now: number = Date.now()): string {
  const day = dateKey(iso, timeZone);
  const time = formatTime(iso, timeZone);
  if (day === dateKey(now, timeZone)) return `Сегодня ${time}`;
  if (day === dateKey(now + 86_400_000, timeZone)) return `Завтра ${time}`;
  const weekday = fmt(timeZone, { weekday: 'short' }).format(new Date(iso));
  return `${capitalize(weekday)} ${time}`;
}

/** «Пт, 17 октября». */
export function formatDayShort(iso: string, timeZone: string): string {
  const weekday = fmt(timeZone, { weekday: 'short' }).format(new Date(iso));
  const date = fmt(timeZone, { day: 'numeric', month: 'long' }).format(new Date(iso));
  return `${capitalize(weekday)}, ${date}`;
}

/** «Среда, 15 октября» (разделитель дней в ленте). */
export function formatDayLong(iso: string | number, timeZone: string): string {
  return capitalize(
    fmt(timeZone, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date(iso)),
  );
}

/** «Пятница, 17 окт» (заголовок графика). */
export function formatDayHeading(date: string): string {
  const d = new Date(`${date}T12:00:00Z`);
  const weekday = fmt('UTC', { weekday: 'long' }).format(d);
  const rest = fmt('UTC', { day: 'numeric', month: 'short' }).format(d).replace('.', '');
  return `${capitalize(weekday)}, ${rest}`;
}

/** Время для списка чатов: «14:03», «вчера», «ср», «12.10». */
export function formatListTime(iso: string, timeZone: string, now: number = Date.now()): string {
  const day = dateKey(iso, timeZone);
  if (day === dateKey(now, timeZone)) return formatTime(iso, timeZone);
  if (day === dateKey(now - 86_400_000, timeZone)) return 'вчера';
  if (Date.parse(iso) > now - 6 * 86_400_000)
    return fmt(timeZone, { weekday: 'short' }).format(new Date(iso));
  return fmt(timeZone, { day: '2-digit', month: '2-digit' }).format(new Date(iso));
}

/** «9 000 ₸» из тиынов. */
export function formatMoney(money: { amount: number; currency: string } | null): string {
  if (!money) return 'цена по запросу';
  const value = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(
    money.amount / 100,
  );
  return `${value} ${money.currency === 'KZT' ? '₸' : money.currency}`;
}

/** «0:07» для длительности голосового. */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** «1 ч 20 мин», «30 мин». */
export function formatMinutes(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m} мин`;
  return m === 0 ? `${h} ч` : `${h} ч ${m} мин`;
}
