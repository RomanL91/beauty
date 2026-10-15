import { describe, expect, it } from 'vitest';
import {
  formatDayHeading,
  formatDuration,
  formatMinutes,
  formatMoney,
  formatSlotShort,
  formatTime,
} from './format';

const TZ = 'Asia/Almaty';
const now = Date.parse('2026-10-14T09:00:00+05:00'); // ср

describe('format', () => {
  it('время в поясе мастера', () => {
    expect(formatTime('2026-10-17T07:00:00Z', TZ)).toBe('12:00');
  });
  it('короткая подпись окна', () => {
    expect(formatSlotShort('2026-10-14T18:00:00+05:00', TZ, now)).toBe('Сегодня 18:00');
    expect(formatSlotShort('2026-10-15T12:00:00+05:00', TZ, now)).toBe('Завтра 12:00');
    expect(formatSlotShort('2026-10-16T12:00:00+05:00', TZ, now)).toBe('Пт 12:00');
  });
  it('заголовок дня графика', () => {
    expect(formatDayHeading('2026-10-16')).toBe('Пятница, 16 окт');
  });
  it('деньги, длительность, минуты', () => {
    expect(formatMoney({ amount: 900000, currency: 'KZT' }).replace(/\s/g, ' ')).toBe('9 000 ₸');
    expect(formatDuration(7)).toBe('0:07');
    expect(formatMinutes(80)).toBe('1 ч 20 мин');
    expect(formatMinutes(150)).toBe('2 ч 30 мин');
  });
});
