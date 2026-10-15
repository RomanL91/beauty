import { describe, expect, it } from 'vitest';
import { formatRemainingClock, formatRemainingLong, remaining } from './countdown';

const deadline = '2026-10-15T12:00:00Z';
const at = (iso: string) => Date.parse(iso);

describe('таймер автоотклонения', () => {
  it('часы и минуты, округление вверх до минуты', () => {
    expect(formatRemainingLong(remaining(deadline, at('2026-10-15T10:20:00Z')))).toBe('1 ч 40 мин');
    expect(formatRemainingLong(remaining(deadline, at('2026-10-15T10:20:30Z')))).toBe('1 ч 40 мин');
    expect(formatRemainingLong(remaining(deadline, at('2026-10-15T11:00:00Z')))).toBe('1 ч');
    expect(formatRemainingLong(remaining(deadline, at('2026-10-15T11:48:00Z')))).toBe('12 мин');
  });

  it('последняя минута и истечение', () => {
    expect(formatRemainingLong(remaining(deadline, at('2026-10-15T11:59:30Z')))).toBe(
      'меньше минуты',
    );
    const done = remaining(deadline, at('2026-10-15T12:00:05Z'));
    expect(done.expired).toBe(true);
    expect(done.ms).toBe(0);
    expect(formatRemainingLong(done)).toBe('время вышло');
  });

  it('новый срок с сервера сразу меняет отсчёт', () => {
    const now = at('2026-10-15T11:00:00Z');
    expect(formatRemainingLong(remaining(deadline, now))).toBe('1 ч');
    expect(formatRemainingLong(remaining('2026-10-15T11:30:00Z', now))).toBe('30 мин');
  });

  it('часы кода входа m:ss', () => {
    expect(
      formatRemainingClock(remaining('2026-10-15T10:05:00Z', at('2026-10-15T10:00:09Z'))),
    ).toBe('4:51');
  });
});
