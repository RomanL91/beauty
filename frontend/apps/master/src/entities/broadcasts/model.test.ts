import { ApiError, type Broadcast } from '@beauty/api';
import { describe, expect, it } from 'vitest';
import { broadcastErrorText, broadcastStatusText, recipientsText } from './model';

const base: Broadcast = {
  id: 'b1',
  text: 'Скидка',
  photo_url: null,
  status: 'draft',
  origin: 'master',
  recipients: 3,
  delivered: 0,
  created_at: '2026-10-20T10:00:00Z',
  started_at: null,
  finished_at: null,
};

describe('рассылки', () => {
  it('получатели и статус', () => {
    expect([recipientsText(1), recipientsText(3), recipientsText(11)]).toEqual([
      '1 клиенту',
      '3 клиентам',
      '11 клиентам',
    ]);
    expect(broadcastStatusText(base)).toBe('Черновик');
    expect(broadcastStatusText({ ...base, status: 'sending', delivered: 1 })).toBe(
      'Отправляется · 1 из 3',
    );
    expect(broadcastStatusText({ ...base, status: 'sent', delivered: 21 })).toBe(
      'Отправлено 21 клиенту',
    );
  });

  it('ошибки отправки — по коду', () => {
    const problem = (code: string, status = 409) =>
      ApiError.fromBody(status, { type: 'about:blank', title: code, status, code });
    expect(broadcastErrorText(problem('broadcast_cooldown', 429))).toMatch(
      /одной рассылки в сутки/,
    );
    expect(broadcastErrorText(problem('broadcasts_blocked', 403))).toMatch(/отключены/);
    expect(broadcastErrorText(problem('no_recipients'))).toMatch(/клиентов ещё нет/);
    expect(broadcastErrorText(new Error('boom'))).toBe('Не получилось — попробуйте ещё раз');
  });
});
