import { describe, expect, it, vi } from 'vitest';
import type { SessionResponse } from '../types';
import { SessionStore } from './session-store';

const session = (token: string): SessionResponse => ({
  account_id: 'acc-1',
  access_token: token,
  token_type: 'Bearer',
  expires_at: new Date(Date.now() + 60_000).toISOString(),
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('SessionStore', () => {
  it('параллельные refresh схлопываются в один запрос', async () => {
    const gate = deferred<{ session: SessionResponse }>();
    const refresher = vi.fn(() => gate.promise);
    const store = new SessionStore(refresher);
    store.accept(session('old'));

    const all = Promise.all([store.refresh('old'), store.refresh('old'), store.refresh('old')]);
    gate.resolve({ session: session('new') });

    expect(await all).toEqual([true, true, true]);
    expect(refresher).toHaveBeenCalledTimes(1);
    expect(store.accessToken).toBe('new');
  });

  it('не обновляет, если токен уже сменился после запроса', async () => {
    const refresher = vi.fn(async () => ({ session: session('newer') }));
    const store = new SessionStore(refresher);
    store.accept(session('fresh'));

    await expect(store.refresh('stale')).resolves.toBe(true);
    expect(refresher).not.toHaveBeenCalled();
  });

  it('после завершённого refresh следующий снова идёт на сервер', async () => {
    let n = 0;
    const store = new SessionStore(async () => ({ session: session(`t${++n}`) }));
    await store.refresh();
    await store.refresh();
    expect(store.accessToken).toBe('t2');
  });

  it('reuse → анонимная сессия с причиной reuse', async () => {
    const store = new SessionStore(async () => ({ rejected: 'reuse' as const }));
    store.accept(session('a'));
    const listener = vi.fn();
    store.subscribe(listener);

    await expect(store.refresh('a')).resolves.toBe(false);
    expect(store.accessToken).toBeNull();
    expect(store.getSnapshot()).toEqual({ status: 'anonymous', reason: 'reuse' });
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('отказ при восстановлении на старте — без причины (не «сессия истекла»)', async () => {
    const store = new SessionStore(async () => ({ rejected: 'expired' as const }));
    await store.refresh();
    expect(store.getSnapshot()).toEqual({ status: 'anonymous', reason: null });
  });

  it('сетевая ошибка refresh пробрасывается и не сбрасывает сессию', async () => {
    const store = new SessionStore(async () => {
      throw new TypeError('offline');
    });
    store.accept(session('keep'));
    await expect(store.refresh('keep')).rejects.toThrow('offline');
    expect(store.accessToken).toBe('keep');
  });
});
