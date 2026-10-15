import { setupWorker } from 'msw/browser';
import { createMockApi, type MockScope } from './index';
import type { KeyValueStore } from './db';

/** «Cookie» мок-сессии в localStorage — переживает перезагрузку, как настоящий refresh. */
function localStore(): KeyValueStore {
  return {
    get: (k) => {
      try {
        return localStorage.getItem(k);
      } catch {
        return null;
      }
    },
    set: (k, v) => {
      try {
        localStorage.setItem(k, v);
      } catch {
        /* приватный режим */
      }
    },
    remove: (k) => {
      try {
        localStorage.removeItem(k);
      } catch {
        /* приватный режим */
      }
    },
  };
}

/**
 * Запустить MSW в браузере (dev/e2e).
 *
 * Запросы вне обработчиков (Vite, шрифты, реальный вход в режиме `auth: false`)
 * пропускаются в сеть.
 */
export async function startMockWorker(scope: MockScope): Promise<void> {
  const { handlers } = createMockApi({ scope, storage: localStore() });
  const worker = setupWorker(...handlers);
  await worker.start({ onUnhandledFrame: 'bypass', quiet: true });
}
