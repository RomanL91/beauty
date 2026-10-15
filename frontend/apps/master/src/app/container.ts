import {
  HttpAssistantGateway,
  HttpCore,
  HttpInboxGateway,
  HttpMasterEventsGateway,
  HttpPushGateway,
  HttpScheduleGateway,
  StubMasterAuthGateway,
  type AssistantGateway,
  type AuthGateway,
  type InboxGateway,
  type MasterEventsGateway,
  type PushGateway,
  type ScheduleGateway,
  type SessionStore,
} from '@beauty/api';
import type { AppEnv } from '../shared/config/env';

/** Зависимости кабинета мастера: компоненты знают только порты. */
export interface MasterContainer {
  readonly env: AppEnv;
  readonly session: SessionStore;
  /** Итерация 1: заглушка входа (см. StubMasterAuthGateway). */
  readonly auth: AuthGateway;
  readonly schedule: ScheduleGateway;
  readonly inbox: InboxGateway;
  readonly assistant: AssistantGateway;
  readonly events: MasterEventsGateway;
  readonly push: PushGateway;
}

/** Собрать контейнер на HTTP-адаптерах. */
export function createMasterContainer(env: AppEnv, core = new HttpCore()): MasterContainer {
  return {
    env,
    session: core.session,
    auth: new StubMasterAuthGateway(core),
    schedule: new HttpScheduleGateway(core),
    inbox: new HttpInboxGateway(core),
    assistant: new HttpAssistantGateway(core),
    events: new HttpMasterEventsGateway(core),
    push: new HttpPushGateway(core),
  };
}
