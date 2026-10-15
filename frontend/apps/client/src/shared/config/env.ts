/** Режим работы с API: `mock` — MSW (кроме входа), `real` — настоящий бэкенд. */
export type ApiMode = 'mock' | 'real';

/** Настройки сборки (из `VITE_*`). */
export interface AppEnv {
  readonly apiMode: ApiMode;
  /** Мокать ли вход через Telegram. */
  readonly mockAuth: boolean;
  /** Мастер по умолчанию, если в адресе его нет (только dev). */
  readonly defaultMaster: string | null;
  readonly vapidPublicKey: string | null;
}

/** Прочитать окружение Vite. */
export function readEnv(): AppEnv {
  const env = import.meta.env;
  return {
    apiMode: env.VITE_API_MODE === 'real' ? 'real' : 'mock',
    mockAuth: env.VITE_MOCK_AUTH === '1' || env.VITE_MOCK_AUTH === 'true',
    defaultMaster: env.VITE_DEFAULT_MASTER || null,
    vapidPublicKey: env.VITE_VAPID_PUBLIC_KEY || null,
  };
}
