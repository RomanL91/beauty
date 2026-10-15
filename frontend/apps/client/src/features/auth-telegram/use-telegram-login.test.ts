import { describe, expect, it } from 'vitest';
import { loginReducer, type LoginState } from './use-telegram-login';

const challenge = {
  challenge_id: 'c',
  deep_link: 'https://t.me/bot?start=x',
  confirmation_code: '47',
  expires_at: '2026-10-15T12:05:00Z',
};

describe('loginReducer', () => {
  const waiting = loginReducer({ step: 'starting' }, { type: 'started', challenge });

  it('pending → claimed → confirmed → completed (обмен)', () => {
    let s: LoginState = waiting;
    s = loginReducer(s, { type: 'status', status: 'claimed' });
    expect(s).toMatchObject({ step: 'waiting', status: 'claimed' });
    s = loginReducer(s, { type: 'status', status: 'confirmed' });
    s = loginReducer(s, { type: 'status', status: 'completed' });
    expect(s).toEqual({ step: 'exchanging', challenge });
    expect(loginReducer(s, { type: 'exchanged' })).toEqual({ step: 'signed-in' });
  });

  it('чужой код и истечение — ошибка с причиной', () => {
    expect(loginReducer(waiting, { type: 'status', status: 'rejected' })).toMatchObject({
      step: 'failed',
      reason: 'rejected',
    });
    expect(loginReducer(waiting, { type: 'status', status: 'expired' })).toMatchObject({
      step: 'failed',
      reason: 'expired',
    });
  });

  it('обрыв SSE отражается, поздние события после выхода из ожидания игнорируются', () => {
    const s = loginReducer(waiting, { type: 'stream', stream: 'reconnecting' });
    expect(s).toMatchObject({ stream: 'reconnecting' });
    const done = loginReducer(s, { type: 'status', status: 'completed' });
    expect(loginReducer(done, { type: 'status', status: 'expired' })).toBe(done);
  });
});
