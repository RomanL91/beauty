/** Оставшееся время до срока. */
export interface Remaining {
  /** Миллисекунды до срока (не меньше 0). */
  readonly ms: number;
  readonly expired: boolean;
  readonly hours: number;
  readonly minutes: number;
  readonly seconds: number;
}

/**
 * Сколько осталось до `deadline` от `now`.
 *
 * Тикает локально от серверного срока (`auto_decline_at`, `hold_until`,
 * `expires_at`): сам срок не пересчитывается на клиенте, поэтому событие SSE
 * с новым сроком просто подменяет `deadline`.
 */
export function remaining(deadline: string, now: number): Remaining {
  const ms = Math.max(0, Date.parse(deadline) - now);
  const total = Math.floor(ms / 1000);
  return {
    ms,
    expired: ms === 0,
    hours: Math.floor(total / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  };
}

/** «1 ч 40 мин», «12 мин», «меньше минуты». */
export function formatRemainingLong(left: Remaining): string {
  if (left.expired) return 'время вышло';
  if (left.hours === 0 && left.minutes === 0) return 'меньше минуты';
  // Округляем вверх до минуты: «через 1 ч 40 мин», пока не прошла 40-я минута.
  const totalMinutes = Math.ceil(left.ms / 60_000);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h === 0) return `${m} мин`;
  return m === 0 ? `${h} ч` : `${h} ч ${m} мин`;
}

/** «4:51» (для таймера кода входа). */
export function formatRemainingClock(left: Remaining): string {
  const minutes = left.hours * 60 + left.minutes;
  return `${minutes}:${String(left.seconds).padStart(2, '0')}`;
}
