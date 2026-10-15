import { call, unwrap, type HttpCore } from '../http/client';
import { SseConnection } from '../sse/sse-connection';
import type { AuthGateway, ChallengeWatchHandlers } from '../ports/auth-gateway';
import type { Unsubscribe } from '../ports/common';
import {
  FINAL_CHALLENGE_STATUSES,
  type ChallengeStatus,
  type ChallengeStatusEvent,
  type ChallengeStatusResponse,
  type SessionResponse,
  type StartChallengeResponse,
} from '../types';

/** Интервал опроса статуса, пока SSE недоступен. */
const POLL_INTERVAL_MS = 3000;

/**
 * Адаптер входа через Telegram поверх реального API identity.
 *
 * Cookie (`bk_auth_challenge`, `bk_refresh`) ставит и читает сервер: запросы
 * идут на тот же origin, браузер прикладывает их сам.
 */
export class HttpAuthGateway implements AuthGateway {
  constructor(private readonly core: HttpCore) {}

  startChallenge(): Promise<StartChallengeResponse> {
    return unwrap(() => this.core.bare.POST('/auth/telegram/challenges'));
  }

  getChallengeStatus(challengeId: string): Promise<ChallengeStatusResponse> {
    return unwrap(() =>
      this.core.bare.GET('/auth/telegram/challenges/{challenge_id}', {
        params: { path: { challenge_id: challengeId } },
      }),
    );
  }

  watchChallenge(challengeId: string, handlers: ChallengeWatchHandlers): Unsubscribe {
    let last: ChallengeStatus | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let stopped = false;

    const emit = (status: ChallengeStatus): void => {
      if (stopped || status === last) return;
      last = status;
      handlers.onStatus(status);
      if (FINAL_CHALLENGE_STATUSES.has(status)) stop();
    };
    const poll = (): void => {
      this.getChallengeStatus(challengeId).then(
        (view) => emit(view.status),
        () => undefined,
      );
    };
    const startPolling = (): void => {
      if (pollTimer !== null || stopped) return;
      poll();
      pollTimer = setInterval(poll, POLL_INTERVAL_MS);
    };
    const stopPolling = (): void => {
      if (pollTimer !== null) clearInterval(pollTimer);
      pollTimer = null;
    };

    const connection = new SseConnection({
      url: this.core.url(`/auth/telegram/challenges/${encodeURIComponent(challengeId)}/events`),
      fetch: (request) => globalThis.fetch(request),
      retryMs: 1000,
      maxRetryMs: 10_000,
      onFrame: (frame) => {
        if (frame.event !== 'status') return;
        const payload = JSON.parse(frame.data) as ChallengeStatusEvent;
        emit(payload.status);
      },
      onStateChange: (state) => {
        handlers.onStreamState?.(state);
        if (state === 'open') stopPolling();
        if (state === 'reconnecting') startPolling();
      },
      onFatal: () => startPolling(),
    }).start();

    function stop(): void {
      stopped = true;
      stopPolling();
      connection.close();
    }
    return stop;
  }

  async exchangeChallenge(challengeId: string): Promise<SessionResponse> {
    const session = await unwrap(() =>
      this.core.bare.POST('/auth/telegram/challenges/{challenge_id}/session', {
        params: { path: { challenge_id: challengeId } },
      }),
    );
    this.core.session.accept(session);
    return session;
  }

  async restoreSession(): Promise<boolean> {
    try {
      return await this.core.session.refresh();
    } catch {
      // Офлайн: не знаем, жива ли сессия. Остаёмся анонимными до сети.
      this.core.session.signOut(null);
      return false;
    }
  }

  async logout(): Promise<void> {
    try {
      await call(() => this.core.bare.POST('/auth/session/logout'));
    } finally {
      this.core.session.signOut('logout');
    }
  }
}
