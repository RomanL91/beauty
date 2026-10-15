import {
  ApiError,
  type ChallengeStatus,
  type StartChallengeResponse,
  type StreamState,
} from '@beauty/api';
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { useContainer } from '../../shared/lib/container-context';

/** Состояние экрана входа. */
export type LoginState =
  | { readonly step: 'starting' }
  | { readonly step: 'start-failed'; readonly offline: boolean }
  | {
      readonly step: 'waiting';
      readonly challenge: StartChallengeResponse;
      readonly status: ChallengeStatus;
      readonly stream: StreamState;
    }
  | { readonly step: 'exchanging'; readonly challenge: StartChallengeResponse }
  | { readonly step: 'signed-in' }
  | {
      readonly step: 'failed';
      readonly challenge: StartChallengeResponse;
      readonly reason: 'rejected' | 'expired' | 'exchange';
    };

type Action =
  | { type: 'start' }
  | { type: 'started'; challenge: StartChallengeResponse }
  | { type: 'start-failed'; offline: boolean }
  | { type: 'status'; status: ChallengeStatus }
  | { type: 'stream'; stream: StreamState }
  | { type: 'exchanged' }
  | { type: 'exchange-failed' };

/** Переходы экрана входа (чистая функция — проверяется тестами). */
export function loginReducer(state: LoginState, action: Action): LoginState {
  switch (action.type) {
    case 'start':
      return { step: 'starting' };
    case 'started':
      return {
        step: 'waiting',
        challenge: action.challenge,
        status: 'pending',
        stream: 'connecting',
      };
    case 'start-failed':
      return { step: 'start-failed', offline: action.offline };
    case 'stream':
      return state.step === 'waiting' ? { ...state, stream: action.stream } : state;
    case 'status': {
      if (state.step !== 'waiting') return state;
      if (action.status === 'completed') return { step: 'exchanging', challenge: state.challenge };
      if (action.status === 'rejected' || action.status === 'expired') {
        return { step: 'failed', challenge: state.challenge, reason: action.status };
      }
      // consumed — вход уже обменян (например, в другой вкладке): начать заново.
      if (action.status === 'consumed')
        return { step: 'failed', challenge: state.challenge, reason: 'expired' };
      return { ...state, status: action.status };
    }
    case 'exchanged':
      return { step: 'signed-in' };
    case 'exchange-failed':
      return state.step === 'exchanging'
        ? { step: 'failed', challenge: state.challenge, reason: 'exchange' }
        : state;
  }
}

/**
 * Вход через Telegram: старт challenge → ожидание подтверждения в боте (SSE,
 * при обрыве — опрос) → обмен на сессию. Таймер истечения тикает в UI от
 * `expires_at`; когда он вышел, считаем вход истёкшим, не дожидаясь сервера.
 */
export function useTelegramLogin() {
  const { auth } = useContainer();
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

  const expire = useCallback(() => dispatch({ type: 'status', status: 'expired' }), []);

  return { state, restart: begin, expire };
}
