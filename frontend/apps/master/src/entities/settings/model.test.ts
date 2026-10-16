import { ApiError } from '@beauty/api';
import { describe, expect, it } from 'vitest';
import {
  intervalsError,
  intervalsText,
  pageUrl,
  parseTenge,
  saveErrorText,
  tengeText,
  weekDraft,
  weekErrors,
  workingDays,
} from './model';

describe('цены: тенге ↔ тиыны', () => {
  it('ввод в тенге превращается в тиыны', () => {
    expect(parseTenge('12000')).toEqual({ amount: 1_200_000, currency: 'KZT' });
    expect(parseTenge('12 000 ₸')).toEqual({ amount: 1_200_000, currency: 'KZT' });
    expect(parseTenge('9500,5')).toEqual({ amount: 950_050, currency: 'KZT' });
    expect(parseTenge('  ')).toBeNull();
    expect(parseTenge('дорого')).toBeUndefined();
    expect(parseTenge('-5')).toBeUndefined();
    expect(parseTenge('1,234')).toBeUndefined();
  });

  it('тиыны показываются в тенге без лишних нулей', () => {
    expect(tengeText({ amount: 1_200_000, currency: 'KZT' })).toBe('12000');
    expect(tengeText({ amount: 950_005, currency: 'KZT' })).toBe('9500,05');
    expect(tengeText(null)).toBe('');
    const price = { amount: 1_234_550, currency: 'KZT' as const };
    expect(parseTenge(tengeText(price))).toEqual(price);
  });
});

describe('график', () => {
  it('интервалы дня: формат, кратность 5, порядок, пересечения', () => {
    expect(
      intervalsError([
        { start: '15:00', end: '19:00' },
        { start: '10:00', end: '14:00' },
      ]),
    ).toBeNull();
    expect(intervalsError([{ start: '10:00', end: '25:00' }])).toBe('Время — в формате ЧЧ:ММ');
    expect(intervalsError([{ start: '10:03', end: '12:00' }])).toBe('Минуты — кратные 5');
    expect(intervalsError([{ start: '12:00', end: '12:00' }])).toBe(
      'Начало должно быть раньше конца',
    );
    expect(
      intervalsError([
        { start: '10:00', end: '14:00' },
        { start: '13:30', end: '15:00' },
      ]),
    ).toBe('Интервалы пересекаются');
  });

  it('неделя: черновик на 7 дней и обратно, выходные не отправляются', () => {
    const draft = weekDraft([
      { weekday: 2, intervals: [{ start: '12:00', end: '20:00' }] },
      { weekday: 0, intervals: [{ start: '10:00', end: '19:00' }] },
    ]);
    expect(draft).toHaveLength(7);
    expect(draft[1]).toEqual([]);
    draft[0] = [
      { start: '15:00', end: '19:00' },
      { start: '10:00', end: '14:00' },
    ];
    expect(workingDays(draft)).toEqual([
      {
        weekday: 0,
        intervals: [
          { start: '10:00', end: '14:00' },
          { start: '15:00', end: '19:00' },
        ],
      },
      { weekday: 2, intervals: [{ start: '12:00', end: '20:00' }] },
    ]);
    expect(weekErrors(draft).every((e) => e === null)).toBe(true);
    expect(intervalsText(draft[0])).toBe('15:00–19:00, 10:00–14:00');
    expect(intervalsText([])).toBe('выходной');
  });
});

describe('прочее', () => {
  it('адрес страницы — поддомен мастера рядом с кабинетом', () => {
    expect(pageUrl('alisa', { protocol: 'http:', host: 'master.localhost:8080' })).toBe(
      'http://alisa.localhost:8080/',
    );
    expect(pageUrl('alisa', { protocol: 'https:', host: 'master.beautiful.kz' })).toBe(
      'https://alisa.beautiful.kz/',
    );
    expect(pageUrl('alisa', { protocol: 'http:', host: 'localhost:5174' })).toBe(
      'https://alisa.beautiful.kz/',
    );
  });

  it('ошибки сохранения понятны мастеру', () => {
    expect(saveErrorText(ApiError.network())).toBe('Нет соединения — изменения не сохранены');
    expect(saveErrorText(new ApiError(422, 'invalid_schedule', 'Интервал пустой'))).toBe(
      'Интервал пустой',
    );
    expect(saveErrorText(new ApiError(413, 'photo_too_large', 'too large'))).toBe(
      'Фото больше 8 МБ',
    );
  });
});
