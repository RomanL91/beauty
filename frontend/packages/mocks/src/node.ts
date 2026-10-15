import { setupServer } from 'msw/node';
import { createMockApi } from './index';
import type { MockDbOptions } from './db';

/** MSW для Vitest: сервер и база (для проверок состояния). */
export function createMockServer(options: MockDbOptions = {}) {
  const { db, handlers } = createMockApi({
    agentDelayMs: 10,
    challengeStepMs: 30,
    taskStepMs: 20,
    ...options,
  });
  return { db, server: setupServer(...handlers) };
}
