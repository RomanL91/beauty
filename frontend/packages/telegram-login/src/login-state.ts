import type { ChallengeStatus, StartChallengeResponse, StreamState } from '@beauty/api';

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

/** Действия экрана входа. */
export type LoginAction =
  | { type: 'start' }
  | { type: 'started'; challenge: StartChallengeResponse }
  | { type: 'start-failed'; offline: boolean }
  | { type: 'status'; status: ChallengeStatus }
  | { type: 'stream'; stream: StreamState }
  | { type: 'exchanged' }
  | { type: 'exchange-failed' };

/** Переходы экрана входа (чистая функция — проверяется тестами). */
export function loginReducer(state: LoginState, action: LoginAction): LoginState {
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
