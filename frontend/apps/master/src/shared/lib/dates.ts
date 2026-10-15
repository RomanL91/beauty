/** Часовой пояс по умолчанию (пока не загружен профиль мастера). */
export const DEFAULT_TZ = 'Asia/Almaty';

/** Сдвиг даты `YYYY-MM-DD` на N дней. */
export function addDays(date: string, days: number): string {
  return new Date(Date.parse(`${date}T12:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);
}

/** Понедельник недели даты. */
export function mondayOf(date: string): string {
  const weekday = (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;
  return addDays(date, -weekday);
}

/** Корректна ли дата `YYYY-MM-DD`. */
export function isDate(value: string | undefined): value is string {
  return (
    value !== undefined && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value))
  );
}

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

/** Короткое имя дня недели. */
export function weekdayShort(date: string): string {
  return WEEKDAYS[(new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7] ?? '';
}
