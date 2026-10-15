import { ApiError } from '../http/api-error';
import type { RequestFetch } from '../http/authorized-fetch';
import { SseParser, type SseFrame } from './sse-parser';

/** Состояние соединения — для индикатора «переподключаемся». */
export type SseConnectionState = 'connecting' | 'open' | 'reconnecting' | 'closed';

/** Настройки потока. */
export interface SseOptions {
  readonly url: string;
  /** `fetch` (обычно — с access-токеном). */
  readonly fetch: RequestFetch;
  /** Кадр с данными. */
  readonly onFrame: (frame: SseFrame) => void;
  readonly onStateChange?: (state: SseConnectionState) => void;
  /** Неустранимая ошибка (4xx кроме 401/408/429): поток остановлен. */
  readonly onFatal?: (error: ApiError) => void;
  /** С какого события продолжить (`Last-Event-ID`). */
  readonly lastEventId?: string | null;
  /** Начальная пауза перед переподключением; сервер может поменять её через `retry:`. */
  readonly retryMs?: number;
  /** Потолок экспоненциальной паузы. */
  readonly maxRetryMs?: number;
  /** Переподключаться ли, когда сервер штатно закрыл поток. */
  readonly reconnectOnEnd?: boolean;
}

/**
 * SSE-поток поверх `fetch` (а не `EventSource`): так можно передать
 * `Authorization` и пережить refresh токена.
 *
 * Переподключается с экспоненциальной паузой и `Last-Event-ID`; после
 * успешного открытия пауза сбрасывается. `close()` останавливает всё.
 */
export class SseConnection {
  readonly #options: SseOptions;
  readonly #abort = new AbortController();
  #retryMs: number;
  #attempt = 0;
  #lastId: string | null;
  #state: SseConnectionState = 'connecting';
  #timer: ReturnType<typeof setTimeout> | null = null;

  constructor(options: SseOptions) {
    this.#options = options;
    this.#retryMs = options.retryMs ?? 3000;
    this.#lastId = options.lastEventId ?? null;
  }

  /** Последний полученный `id`. */
  get lastEventId(): string | null {
    return this.#lastId;
  }

  /** Открыть поток (возвращает себя для цепочки). */
  start(): this {
    void this.#run();
    return this;
  }

  /** Закрыть поток навсегда. */
  close(): void {
    if (this.#state === 'closed') return;
    this.#abort.abort();
    if (this.#timer !== null) clearTimeout(this.#timer);
    this.#setState('closed');
  }

  async #run(): Promise<void> {
    while (!this.#abort.signal.aborted) {
      const ended = await this.#connectOnce();
      if (this.#abort.signal.aborted) return;
      if (ended === 'fatal') return;
      if (ended === 'end' && this.#options.reconnectOnEnd === false) {
        this.#setState('closed');
        return;
      }
      this.#setState('reconnecting');
      await this.#sleep(this.#nextDelay());
    }
  }

  async #connectOnce(): Promise<'end' | 'error' | 'fatal'> {
    const headers = new Headers({ Accept: 'text/event-stream', 'Cache-Control': 'no-store' });
    if (this.#lastId !== null) headers.set('Last-Event-ID', this.#lastId);
    let response: Response;
    try {
      response = await this.#options.fetch(
        new Request(this.#options.url, { headers, signal: this.#abort.signal }),
      );
    } catch {
      return 'error';
    }
    if (!response.ok || response.body === null) {
      const fatal =
        response.status >= 400 && response.status < 500 && ![408, 429].includes(response.status);
      if (fatal) {
        const body: unknown = await response.json().catch(() => null);
        this.#options.onFatal?.(ApiError.fromBody(response.status, body));
        this.close();
        return 'fatal';
      }
      return 'error';
    }

    this.#attempt = 0;
    this.#setState('open');
    const parser = new SseParser(
      (frame) => {
        this.#lastId = frame.id;
        this.#options.onFrame(frame);
      },
      (ms) => {
        this.#retryMs = ms;
      },
      this.#lastId,
    );
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return 'end';
        parser.push(value);
      }
    } catch {
      return 'error';
    } finally {
      reader.releaseLock();
    }
  }

  #nextDelay(): number {
    const max = this.#options.maxRetryMs ?? 30_000;
    const delay = Math.min(this.#retryMs * 2 ** this.#attempt, max);
    this.#attempt += 1;
    // Небольшой разброс, чтобы клиенты не переподключались строем.
    return delay * (0.8 + Math.random() * 0.4);
  }

  #sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
      this.#timer = setTimeout(() => {
        this.#timer = null;
        resolve();
      }, ms);
    });
  }

  #setState(state: SseConnectionState): void {
    if (this.#state === state || this.#state === 'closed') return;
    this.#state = state;
    this.#options.onStateChange?.(state);
  }
}
