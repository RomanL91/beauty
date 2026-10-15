import { ApiError } from '../http/api-error';
import type { HttpCore } from '../http/client';
import type { AuthGateway } from '../ports/auth-gateway';
import type { Unsubscribe } from '../ports/common';
import type { ChallengeStatusResponse, SessionResponse, StartChallengeResponse } from '../types';

/** Учётная запись мастера-заглушки (совпадает с фикстурами MSW). */
export const STUB_MASTER_ACCOUNT_ID = '0192a0c0-0000-7000-8000-00000000a115';

/**
 * Заглушка входа мастера на итерацию 1.
 *
 * Роль мастера появится вместе с контекстом tenancy; до тех пор кабинет
 * открывается локальной сессией, а API мастера отвечает MSW. Интерфейс тот же
 * `AuthGateway` — когда появится настоящий вход, подменится только адаптер.
 */
export class StubMasterAuthGateway implements AuthGateway {
  constructor(private readonly core: HttpCore) {}

  startChallenge(): Promise<StartChallengeResponse> {
    return Promise.reject(unsupported());
  }

  getChallengeStatus(): Promise<ChallengeStatusResponse> {
    return Promise.reject(unsupported());
  }

  watchChallenge(): Unsubscribe {
    return () => undefined;
  }

  exchangeChallenge(): Promise<SessionResponse> {
    return Promise.reject(unsupported());
  }

  restoreSession(): Promise<boolean> {
    this.core.session.accept({
      account_id: STUB_MASTER_ACCOUNT_ID,
      access_token: 'stub-master-access-token',
      token_type: 'Bearer',
      expires_at: new Date(Date.now() + 24 * 3600_000).toISOString(),
    });
    return Promise.resolve(true);
  }

  logout(): Promise<void> {
    this.core.session.signOut('logout');
    return Promise.resolve();
  }
}

function unsupported(): ApiError {
  return new ApiError(501, 'not_implemented', 'Вход мастера появится вместе с ролями');
}
