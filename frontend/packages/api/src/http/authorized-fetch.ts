import type { SessionStore } from './session-store';

/** Функция `fetch`, принимающая готовый `Request` (так её вызывает openapi-fetch). */
export type RequestFetch = (request: Request) => Promise<Response>;

/** `fetch` по умолчанию: берём глобальный в момент вызова (его подменяет MSW в тестах). */
export const globalFetch: RequestFetch = (request) => globalThis.fetch(request);

/**
 * `fetch` с access-токеном и одним повтором после refresh.
 *
 * 1. Подставляет `Authorization: Bearer <access>` (если токен есть).
 * 2. На 401 запускает single-flight refresh и повторяет запрос один раз.
 * 3. Если refresh не удался или повтор снова 401 — сессия завершается
 *    (`SessionStore` переходит в `anonymous`, UI отправит на экран входа).
 */
export function createAuthorizedFetch(
  session: SessionStore,
  baseFetch: RequestFetch = globalFetch,
): RequestFetch {
  return async (request) => {
    const spare = request.clone();
    const token = session.accessToken;
    const response = await baseFetch(withToken(request, token));
    if (response.status !== 401 || token === null) return response;

    const refreshed = await session.refresh(token);
    if (!refreshed) return response;

    const retried = await baseFetch(withToken(spare, session.accessToken));
    if (retried.status === 401) session.signOut('expired');
    return retried;
  };
}

function withToken(request: Request, token: string | null): Request {
  if (token === null) return request;
  const headers = new Headers(request.headers);
  headers.set('Authorization', `Bearer ${token}`);
  return new Request(request, { headers });
}
