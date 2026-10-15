import {
  HttpAuthGateway,
  HttpConversationGateway,
  HttpCore,
  HttpMasterGateway,
  HttpPushGateway,
  type AuthGateway,
  type ConversationGateway,
  type MasterGateway,
  type PushGateway,
  type SessionStore,
} from '@beauty/api';
import type { AppEnv } from '../shared/config/env';

/**
 * Зависимости клиентского приложения. Компоненты получают их через
 * `useContainer()` и знают только порты; адаптеры собираются здесь.
 */
export interface ClientContainer {
  readonly env: AppEnv;
  /** Чья это страница (`null` — мастер не определён). */
  readonly masterSlug: string | null;
  readonly session: SessionStore;
  readonly auth: AuthGateway;
  readonly masters: MasterGateway;
  readonly conversations: ConversationGateway;
  readonly push: PushGateway;
}

/** Собрать контейнер на HTTP-адаптерах. */
export function createClientContainer(
  env: AppEnv,
  masterSlug: string | null,
  core = new HttpCore(),
): ClientContainer {
  return {
    env,
    masterSlug,
    session: core.session,
    auth: new HttpAuthGateway(core),
    masters: new HttpMasterGateway(core),
    conversations: new HttpConversationGateway(core),
    push: new HttpPushGateway(core),
  };
}
