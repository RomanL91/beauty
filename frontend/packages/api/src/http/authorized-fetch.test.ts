import { describe, expect, it, vi } from 'vitest';
import { createAuthorizedFetch } from './authorized-fetch';
import { SessionStore } from './session-store';

const session = (token: string) => ({
  account_id: 'acc',
  access_token: token,
  token_type: 'Bearer',
  expires_at: new Date(Date.now() + 60_000).toISOString(),
});

/** «Сервер»: принимает только текущий валидный токен. */
function server(valid: { token: string }) {
  return vi.fn(async (request: Request) => {
    const auth = request.headers.get('Authorization');
    return auth === `Bearer ${valid.token}`
      ? new Response(JSON.stringify({ ok: true, body: await request.text() }), { status: 200 })
      : new Response(null, { status: 401 });
  });
}

describe('createAuthorizedFetch', () => {
  it('подставляет Bearer и не трогает успешные ответы', async () => {
    const valid = { token: 'a' };
    const store = new SessionStore(vi.fn());
    store.accept(session('a'));
    const fetch = createAuthorizedFetch(store, server(valid));

    const res = await fetch(new Request('http://x/api'));
    expect(res.status).toBe(200);
  });

  it('пять параллельных 401 → один refresh, все повторены с новым токеном', async () => {
    const valid = { token: 'b' };
    const refresher = vi.fn(async () => {
      await new Promise((r) => setTimeout(r, 10));
      return { session: session('b') };
    });
    const store = new SessionStore(refresher);
    store.accept(session('a'));
    const base = server(valid);
    const fetch = createAuthorizedFetch(store, base);

    const responses = await Promise.all(
      Array.from({ length: 5 }, (_, i) =>
        fetch(new Request('http://x/api', { method: 'POST', body: `n${i}` })),
      ),
    );

    expect(responses.map((r) => r.status)).toEqual([200, 200, 200, 200, 200]);
    expect(refresher).toHaveBeenCalledTimes(1);
    // Тело повторного запроса сохранено (запрос клонирован до отправки).
    expect(await responses[3]!.json()).toEqual({ ok: true, body: 'n3' });
    expect(base).toHaveBeenCalledTimes(10);
  });

  it('refresh отклонён → сессия завершена, наружу уходит 401', async () => {
    const store = new SessionStore(async () => ({ rejected: 'expired' as const }));
    store.accept(session('a'));
    const fetch = createAuthorizedFetch(store, server({ token: 'zzz' }));

    const res = await fetch(new Request('http://x/api'));
    expect(res.status).toBe(401);
    expect(store.getSnapshot()).toEqual({ status: 'anonymous', reason: 'expired' });
  });

  it('401 и после refresh → выход', async () => {
    const store = new SessionStore(async () => ({ session: session('still-bad') }));
    store.accept(session('a'));
    const fetch = createAuthorizedFetch(store, server({ token: 'never' }));

    const res = await fetch(new Request('http://x/api'));
    expect(res.status).toBe(401);
    expect(store.getSnapshot().status).toBe('anonymous');
  });

  it('без токена 401 не запускает refresh', async () => {
    const refresher = vi.fn();
    const store = new SessionStore(refresher);
    const fetch = createAuthorizedFetch(store, server({ token: 'a' }));
    expect((await fetch(new Request('http://x/api'))).status).toBe(401);
    expect(refresher).not.toHaveBeenCalled();
  });
});
