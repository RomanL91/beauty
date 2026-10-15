/**
 * Время фикстур: мастер работает в Астане (UTC+5), даты строятся от «сегодня»,
 * чтобы окна и заявки всегда были в будущем относительно запуска.
 */
export const MASTER_TIMEZONE = 'Asia/Almaty';
const OFFSET = '+05:00';
const OFFSET_MS = 5 * 3600_000;

/** Локальная дата мастера `YYYY-MM-DD` со сдвигом в днях. */
export function localDate(offsetDays = 0, now: number = Date.now()): string {
  return new Date(now + OFFSET_MS + offsetDays * 86_400_000).toISOString().slice(0, 10);
}

/** Сдвиг даты `YYYY-MM-DD` на N дней. */
export function addDays(date: string, days: number): string {
  const base = Date.parse(`${date}T00:00:00Z`);
  return new Date(base + days * 86_400_000).toISOString().slice(0, 10);
}

/** День недели даты: 0 — понедельник … 6 — воскресенье. */
export function weekday(date: string): number {
  return (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
}

/** Момент `HH:MM` локальной даты мастера в RFC 3339. */
export function at(date: string, hm: string): string {
  return `${date}T${hm}:00${OFFSET}`;
}

/** Ближайшая дата (начиная с завтра) с нужным днём недели. */
export function nextWeekday(target: number, now: number = Date.now()): string {
  for (let i = 1; i <= 7; i += 1) {
    const date = localDate(i, now);
    if (weekday(date) === target) return date;
  }
  return localDate(1, now);
}

/** RFC 3339 момента `now + ms`. */
export function fromNow(ms: number, now: number = Date.now()): string {
  return new Date(now + ms).toISOString();
}

/** Минуты между двумя моментами. */
export function minutesBetween(start: string, end: string): number {
  return Math.round((Date.parse(end) - Date.parse(start)) / 60_000);
}

/** Сдвиг момента RFC 3339 на N минут (результат — в поясе мастера). */
export function plusMinutes(moment: string, minutes: number): string {
  const shifted = new Date(Date.parse(moment) + minutes * 60_000 + OFFSET_MS);
  return `${shifted.toISOString().slice(0, 19)}${OFFSET}`;
}

/** «пятница, 17 октября» — для текстов агента. */
export function humanDate(date: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  }).format(new Date(`${date}T00:00:00Z`));
}

/** `HH:MM` момента в поясе мастера. */
export function hhmm(moment: string): string {
  return new Date(Date.parse(moment) + OFFSET_MS).toISOString().slice(11, 16);
}
