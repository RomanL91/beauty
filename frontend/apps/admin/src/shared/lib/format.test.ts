import { describe, expect, it } from 'vitest';
import { count, formatDay, formatPhone, formatSeconds } from './format';

describe('форматы панели', () => {
  it('телефон, секунды, день', () => {
    expect(formatPhone('+77011234567')).toBe('+7 701 123 45 67');
    expect(formatPhone(null)).toBe('—');
    expect(formatPhone('12')).toBe('12');
    expect(formatSeconds(2.44)).toBe('2,4 с');
    expect(formatSeconds(null)).toBe('—');
    expect(formatDay('2026-10-20')).toMatch(/^20 окт/);
    const forms = ['заявка', 'заявки', 'заявок'] as const;
    expect([1, 3, 5, 11, 21, 1142].map((n) => count(n, forms))).toEqual([
      '1 заявка',
      '3 заявки',
      '5 заявок',
      '11 заявок',
      '21 заявка',
      '1\u00a0142 заявки',
    ]);
  });
});
