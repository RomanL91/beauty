import createClient, { type Client } from 'openapi-fetch';
import type { paths } from '../schema';
import { ApiError } from './api-error';
import { createAuthorizedFetch, globalFetch, type RequestFetch } from './authorized-fetch';
import { SessionStore, type SessionRefresher } from './session-store';

/** Типизированный клиент openapi-fetch по контракту. */
export type BeautyClient = Client<paths>;

/** Базовый путь API (см. `servers` в контракте). */
export const API_BASE_PATH = '/api/v1';

/** Настройки HTTP-ядра. */
export interface HttpCoreOptions {
  /** Origin API; по умолчанию — текущий (dev: Vite proxy, prod: nginx). */
  readonly origin?: string;
  /** Нижележащий `fetch` (моки в странице, тесты). */
  readonly fetch?: RequestFetch;
}

/**
 * HTTP-ядро приложения: сессия, `fetch` с токеном и два клиента.
 *
 * * `api` — для защищённых и публичных эндпоинтов (с токеном и refresh при 401);
 * * `bare` — без токена: вход и сам refresh (иначе refresh зациклился бы).
 */
export class HttpCore {
  readonly session: SessionStore;
  readonly api: BeautyClient;
  readonly bare: BeautyClient;
  /** `fetch` с токеном — для SSE и multipart вне openapi-fetch. */
  readonly authorizedFetch: RequestFetch;
  /** `fetch` без токена (в mock-режиме — с перехватом моками). */
  readonly baseFetch: RequestFetch;
  readonly baseUrl: string;

  constructor(options: HttpCoreOptions = {}) {
    const baseFetch = options.fetch ?? globalFetch;
    this.baseFetch = baseFetch;
    this.baseUrl = `${options.origin ?? ''}${API_BASE_PATH}`;
    this.bare = createClient<paths>({ baseUrl: this.baseUrl, fetch: baseFetch });
    this.session = new SessionStore(this.#refresher);
    this.authorizedFetch = createAuthorizedFetch(this.session, baseFetch);
    this.api = createClient<paths>({ baseUrl: this.baseUrl, fetch: this.authorizedFetch });
  }

  /** Абсолютный URL эндпоинта (для SSE). */
  url(path: string): string {
    const base = this.baseUrl.startsWith('http') ? this.baseUrl : `${originOf()}${this.baseUrl}`;
    return `${base}${path}`;
  }

  readonly #refresher: SessionRefresher = async () => {
    const { data, error, response } = await call(() => this.bare.POST('/auth/session/refresh'));
    if (data) return { session: data };
    if (response.status === 401) {
      const code = ApiError.fromBody(401, error).code;
      return { rejected: code === 'session_reuse_detected' ? 'reuse' : 'expired' };
    }
    throw ApiError.fromBody(response.status, error);
  };
}

function originOf(): string {
  return typeof location === 'undefined' ? 'http://localhost' : location.origin;
}

/** Выполнить вызов openapi-fetch, превратив сетевой сбой в `ApiError.network`. */
export async function call<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw ApiError.network(cause);
  }
}

/**
 * Результат openapi-fetch → данные или `ApiError`.
 *
 * Для ответов без тела (204) возвращает `undefined`.
 */
export async function unwrap<D>(
  request: () => Promise<{ data?: D; error?: unknown; response: Response }>,
): Promise<D> {
  const { data, error, response } = await call(request);
  if (!response.ok) throw ApiError.fromBody(response.status, error);
  return data as D;
}
