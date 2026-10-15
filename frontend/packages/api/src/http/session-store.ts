import type { SessionResponse } from '../types';

/** Состояние сессии для UI. */
export type SessionState =
  | { readonly status: 'unknown' }
  | { readonly status: 'anonymous'; readonly reason: SignOutReason | null }
  | { readonly status: 'authenticated'; readonly accountId: string };

/** Почему сессия закончилась. */
export type SignOutReason = 'logout' | 'expired' | 'reuse';

/**
 * Обновление access-токена по refresh-cookie.
 *
 * Возвращает новую сессию, `null` — если сервер отказал (401: сессия мертва
 * или обнаружено повторное использование refresh-токена). Сетевые ошибки
 * пробрасывает: при офлайне сессию не сбрасываем.
 */
export type SessionRefresher = () => Promise<
  { session: SessionResponse } | { rejected: 'expired' | 'reuse' }
>;

type Listener = () => void;

/**
 * Хранилище сессии: access-токен только в памяти.
 *
 * Refresh — single-flight: сколько бы запросов ни получили 401 одновременно,
 * на сервер уйдёт один `POST /auth/session/refresh`, остальные дождутся его
 * результата. Состояние подписывается через `subscribe`/`getSnapshot`
 * (совместимо с `useSyncExternalStore`).
 */
export class SessionStore {
  #token: string | null = null;
  #state: SessionState = { status: 'unknown' };
  #inflight: Promise<boolean> | null = null;
  readonly #listeners = new Set<Listener>();

  constructor(private readonly refresher: SessionRefresher) {}

  /** Текущий access-токен (или `null`). */
  get accessToken(): string | null {
    return this.#token;
  }

  /** Снимок состояния для React. */
  getSnapshot = (): SessionState => this.#state;

  /** Подписка на изменения состояния. */
  subscribe = (listener: Listener): (() => void) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  /** Принять новую сессию (после входа или refresh). */
  accept(session: SessionResponse): void {
    this.#token = session.access_token;
    this.#setState(
      this.#state.status === 'authenticated' && this.#state.accountId === session.account_id
        ? this.#state
        : { status: 'authenticated', accountId: session.account_id },
    );
  }

  /** Завершить сессию локально. */
  signOut(reason: SignOutReason | null): void {
    this.#token = null;
    this.#setState({ status: 'anonymous', reason });
  }

  /**
   * Обновить access-токен (single-flight).
   *
   * @param staleToken токен, с которым запрос получил 401. Если с тех пор токен
   *   уже сменился (кто-то обновил раньше), повторный refresh не нужен.
   * @returns `true`, если есть свежий токен.
   */
  refresh(staleToken?: string | null): Promise<boolean> {
    if (staleToken !== undefined && staleToken !== this.#token && this.#token !== null) {
      return Promise.resolve(true);
    }
    this.#inflight ??= this.#doRefresh().finally(() => {
      this.#inflight = null;
    });
    return this.#inflight;
  }

  async #doRefresh(): Promise<boolean> {
    const result = await this.refresher();
    if ('session' in result) {
      this.accept(result.session);
      return true;
    }
    this.signOut(this.#state.status === 'unknown' ? null : result.rejected);
    return false;
  }

  #setState(next: SessionState): void {
    if (next === this.#state) return;
    this.#state = next;
    for (const listener of this.#listeners) listener();
  }
}
