import type {
  ChallengeStatus,
  ChallengeStatusResponse,
  SessionResponse,
  StartChallengeResponse,
} from '../types';
import type { StreamState, Unsubscribe } from './common';

/** Подписчик на статус входа. */
export interface ChallengeWatchHandlers {
  readonly onStatus: (status: ChallengeStatus) => void;
  /** Состояние канала: `reconnecting` — SSE оборвался, идёт опрос GET. */
  readonly onStreamState?: (state: StreamState) => void;
}

/**
 * Порт входа и сессии.
 *
 * Общий для клиента и мастера; мастер в итерации 1 получает адаптер-заглушку.
 */
export interface AuthGateway {
  /** Начать вход через Telegram (сервер ставит cookie браузера). */
  startChallenge(): Promise<StartChallengeResponse>;
  /** Статус входа одним запросом. */
  getChallengeStatus(challengeId: string): Promise<ChallengeStatusResponse>;
  /**
   * Следить за статусом входа: SSE с переподключением, при обрыве — опрос GET.
   * Сам останавливается на финальном статусе.
   */
  watchChallenge(challengeId: string, handlers: ChallengeWatchHandlers): Unsubscribe;
  /** Обменять завершённый вход на сессию и принять её. */
  exchangeChallenge(challengeId: string): Promise<SessionResponse>;
  /** Восстановить сессию по refresh-cookie при старте приложения. */
  restoreSession(): Promise<boolean>;
  /** Выйти. */
  logout(): Promise<void>;
}
