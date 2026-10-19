/**
 * @beauty/mocks — MSW-обработчики по контракту и in-memory «бэкенд».
 *
 * Обработчики типизированы `paths` из `@beauty/api` через openapi-msw:
 * если ответ мока разойдётся с контрактом, проект не скомпилируется.
 */
import type { RequestHandler } from 'msw';
import { MockDb, type MockDbOptions } from './db';
import { adminHandlers } from './handlers/admin';
import { authHandlers } from './handlers/auth';
import { clientHandlers } from './handlers/client';
import { assistantHandlers, masterHandlers } from './handlers/master';
import { publicHandlers } from './handlers/public';
import { pushHandlers } from './handlers/push';

export { MockDb, MockProblem, memoryStore, type KeyValueStore, type MockDbOptions } from './db';
export { DEMO_SLUG, SERVICES } from './fixtures/master-page';
export { CLIENT_CONVERSATION_ID } from './fixtures/client-chat';
export { CONVERSATIONS, DARYA_REQUEST_ID } from './fixtures/master-cabinet';
export { CLIENTS } from './fixtures/people';
export { uuidv7 } from './ids';
export { MOCK_ADMIN_LOGIN, MOCK_ADMIN_PASSWORD } from './admin';

/** Группы эндпоинтов контракта (теги OpenAPI). */
export type EndpointGroup =
  'auth' | 'public' | 'client' | 'master' | 'assistant' | 'push' | 'admin';

/** Все группы. */
export const ALL_GROUPS: readonly EndpointGroup[] = [
  'auth',
  'public',
  'client',
  'master',
  'assistant',
  'push',
  'admin',
];

/** Какие группы уже реализованы бэкендом — их не мокаем, запросы уходят в сеть. */
export interface MockScope {
  readonly real: ReadonlySet<EndpointGroup>;
}

/** Набор обработчиков поверх общей базы (без «реальных» групп). */
export function createHandlers(
  db: MockDb,
  scope: MockScope = { real: new Set() },
): RequestHandler[] {
  const mocked = (group: EndpointGroup) => !scope.real.has(group);
  return [
    ...(mocked('auth') ? authHandlers(db) : []),
    ...(mocked('public') ? publicHandlers(db) : []),
    ...(mocked('client') ? clientHandlers(db) : []),
    ...(mocked('master') ? masterHandlers(db) : []),
    ...(mocked('assistant') ? assistantHandlers(db) : []),
    ...(mocked('push') ? pushHandlers() : []),
    ...(mocked('admin') ? adminHandlers(db) : []),
  ];
}

/** Разобрать список групп из env (`auth,public` / `all` / пусто). */
export function parseGroups(value: string | undefined | null): Set<EndpointGroup> {
  if (!value) return new Set();
  if (value.trim() === 'all') return new Set(ALL_GROUPS);
  return new Set(
    value
      .split(',')
      .map((v) => v.trim())
      .filter((v): v is EndpointGroup => (ALL_GROUPS as readonly string[]).includes(v)),
  );
}

/** База и обработчики одним вызовом. */
export function createMockApi(options: MockDbOptions & { readonly scope?: MockScope } = {}): {
  db: MockDb;
  handlers: RequestHandler[];
} {
  const db = new MockDb(options);
  return { db, handlers: createHandlers(db, options.scope) };
}
