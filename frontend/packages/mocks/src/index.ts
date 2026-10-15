/**
 * @beauty/mocks — MSW-обработчики по контракту и in-memory «бэкенд».
 *
 * Обработчики типизированы `paths` из `@beauty/api` через openapi-msw:
 * если ответ мока разойдётся с контрактом, проект не скомпилируется.
 */
import type { RequestHandler } from 'msw';
import { MockDb, type MockDbOptions } from './db';
import { authHandlers } from './handlers/auth';
import { clientHandlers } from './handlers/client';
import { masterHandlers } from './handlers/master';
import { mediaHandlers } from './handlers/media';
import { publicHandlers } from './handlers/public';
import { pushHandlers } from './handlers/push';

export { MockDb, MockProblem, memoryStore, type KeyValueStore, type MockDbOptions } from './db';
export { DEMO_SLUG, SERVICES } from './fixtures/master-page';
export { CLIENT_CONVERSATION_ID } from './fixtures/client-chat';
export { CONVERSATIONS, DARYA_REQUEST_ID } from './fixtures/master-cabinet';
export { CLIENTS } from './fixtures/people';
export { uuidv7 } from './ids';

/** Какие группы эндпоинтов мокать. */
export interface MockScope {
  /** Вход и сессия; `false` — запросы уходят на реальный API. */
  readonly auth: boolean;
}

/** Набор обработчиков поверх общей базы. */
export function createHandlers(db: MockDb, scope: MockScope = { auth: true }): RequestHandler[] {
  return [
    ...(scope.auth ? authHandlers(db) : []),
    ...publicHandlers(db),
    ...clientHandlers(db),
    ...masterHandlers(db),
    ...pushHandlers(),
    ...mediaHandlers(db),
  ];
}

/** База и обработчики одним вызовом. */
export function createMockApi(options: MockDbOptions & { scope?: MockScope } = {}): {
  db: MockDb;
  handlers: RequestHandler[];
} {
  const db = new MockDb(options);
  return { db, handlers: createHandlers(db, options.scope) };
}
