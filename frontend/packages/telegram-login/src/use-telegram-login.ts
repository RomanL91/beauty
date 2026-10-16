import {
  ApiError,
  formatRemainingClock,
  remaining,
  type AuthGateway,
  type StartChallengeResponse,
} from '@beauty/api';
import { useNow } from '@beauty/ui';
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { loginReducer } from './login-state';

/** Состояние входа для экрана: шаг, перезапуск, оставшееся время кода. */
export type TelegramLogin = ReturnType<typeof useTelegramLogin>;

/**
 * Вход через Telegram: старт challenge → ожидание подтверждения в боте (SSE,
 * при обрыве — опрос) → обмен на сессию. Таймер истечения тикает в UI от
 * `expires_at`; когда он вышел, считаем вход истёкшим, не дожидаясь сервера.
 */
export function useTelegramLogin(auth: AuthGateway) {
  const [state, dispatch] = useReducer(loginReducer, { step: 'starting' });
  const attempt = useRef(0);
  const started = useRef<{ attempt: number; promise: Promise<StartChallengeResponse> } | null>(
    null,
  );

  const begin = useCallback(() => {
    attempt.current += 1;
    started.current = null;
    dispatch({ type: 'start' });
  }, []);

  // Старт. Ref переживает двойной вызов эффектов в StrictMode — второй challenge не создаём.
  useEffect(() => {
    if (state.step !== 'starting') return undefined;
    let cancelled = false;
    if (started.current?.attempt !== attempt.current) {
      started.current = { attempt: attempt.current, promise: auth.startChallenge() };
    }
    started.current.promise.then(
      (challenge) => !cancelled && dispatch({ type: 'started', challenge }),
      (error: unknown) =>
        !cancelled &&
        dispatch({ type: 'start-failed', offline: error instanceof ApiError && error.isNetwork }),
    );
    return () => {
      cancelled = true;
    };
  }, [auth, state.step]);

  // Ожидание подтверждения.
  const challengeId = state.step === 'waiting' ? state.challenge.challenge_id : null;
  useEffect(() => {
    if (!challengeId) return undefined;
    return auth.watchChallenge(challengeId, {
      onStatus: (status) => dispatch({ type: 'status', status }),
      onStreamState: (stream) => dispatch({ type: 'stream', stream }),
    });
  }, [auth, challengeId]);

  // Обмен на сессию.
  const exchangingId = state.step === 'exchanging' ? state.challenge.challenge_id : null;
  useEffect(() => {
    if (!exchangingId) return undefined;
    let cancelled = false;
    auth.exchangeChallenge(exchangingId).then(
      () => !cancelled && dispatch({ type: 'exchanged' }),
      () => !cancelled && dispatch({ type: 'exchange-failed' }),
    );
    return () => {
      cancelled = true;
    };
  }, [auth, exchangingId]);

  // Срок кода тикает в интерфейсе; истёк — вход окончен, не дожидаясь сервера.
  const now = useNow(1000, state.step === 'waiting');
  const left = state.step === 'waiting' ? remaining(state.challenge.expires_at, now) : null;
  useEffect(() => {
    if (left?.expired) dispatch({ type: 'status', status: 'expired' });
  }, [left?.expired]);

  return { state, restart: begin, clock: left ? formatRemainingClock(left) : null };
}
