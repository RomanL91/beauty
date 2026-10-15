import { getResponse } from 'msw';
import type { KeyValueStore } from './db';
import { createMockApi, type MockScope } from './index';

/** «Cookie» мок-сессии в localStorage — переживает перезагрузку, как настоящий refresh. */
function localStore(): KeyValueStore {
  const safe = <T>(run: () => T, fallback: T): T => {
    try {
      return run();
    } catch {
      return fallback;
    }
  };
  return {
    get: (k) => safe(() => localStorage.getItem(k), null),
    set: (k, v) => safe(() => localStorage.setItem(k, v), undefined),
    remove: (k) => safe(() => localStorage.removeItem(k), undefined),
  };
}

/**
 * Моки в самой странице: `fetch`, который сначала ищет ответ в MSW-обработчиках
 * (`getResponse`), а если группа реализована бэкендом или обработчика нет —
 * идёт в сеть. Service worker не нужен, поэтому моки уживаются с PWA-worker.
 */
export function createMockFetch(scope: MockScope): (request: Request) => Promise<Response> {
  const { handlers } = createMockApi({ scope, storage: localStore() });
  return async (request) =>
    (await getResponse(handlers, request.clone())) ?? globalThis.fetch(request);
}
