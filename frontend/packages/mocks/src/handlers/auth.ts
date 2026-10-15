import { delay } from 'msw';
import { FINAL_CHALLENGE_STATUSES, type ChallengeStatus } from '@beauty/api';
import type { MockDb } from '../db';
import { frame, streamFrom } from '../sse';
import { authError, http, run } from './support';

/** Вход через Telegram: сценарий «бот подтвердил» идёт сам по таймеру. */
export function authHandlers(db: MockDb) {
  return [
    http.post('/auth/telegram/challenges', async ({ response }) => {
      await delay(150);
      return response(201).json(db.startChallenge());
    }),

    http.get('/auth/telegram/challenges/{challenge_id}', ({ params, response }) =>
      run(() => {
        const { status, expiresAt } = db.challengeStatus(params.challenge_id);
        return response(200).json({
          challenge_id: params.challenge_id,
          status,
          expires_at: expiresAt,
        });
      }, 'auth'),
    ),

    http.get('/auth/telegram/challenges/{challenge_id}/events', ({ params, request, response }) =>
      run(() => {
        db.challengeStatus(params.challenge_id);
        return response.untyped(
          streamFrom(request, (emit, close) => {
            let last: ChallengeStatus | null = null;
            const tick = (): void => {
              const { status } = db.challengeStatus(params.challenge_id);
              if (status !== last) {
                emit(frame('status', { status }, undefined, last === null ? 3000 : undefined));
                last = status;
              }
              if (FINAL_CHALLENGE_STATUSES.has(status)) close();
            };
            tick();
            const timer = setInterval(tick, Math.min(250, db.challengeStepMs / 3));
            return () => clearInterval(timer);
          }),
        );
      }, 'auth'),
    ),

    http.post('/auth/telegram/challenges/{challenge_id}/session', ({ params, response }) =>
      run(() => response(200).json(db.exchangeChallenge(params.challenge_id)), 'auth'),
    ),

    http.post('/auth/session/refresh', ({ response }) => {
      const session = db.refreshSession();
      return session
        ? response(200).json(session)
        : authError(401, 'invalid_session', 'Сессия недействительна');
    }),

    http.post('/auth/session/logout', ({ response }) => {
      db.logout();
      return response(204).empty();
    }),
  ];
}
