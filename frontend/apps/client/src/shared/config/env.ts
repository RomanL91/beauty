/** Режим работы с API: `mock` — моки (кроме входа), `real` — бэкенд там, где эндпоинты уже есть. */
export type ApiMode = 'mock' | 'real';

/** Настройки сборки (из `VITE_*`). */
export interface AppEnv {
  readonly apiMode: ApiMode;
  /** Мастер по умолчанию, если в адресе его нет (только dev). */
  readonly defaultMaster: string | null;
  readonly vapidPublicKey: string | null;
  /**
   * Группы эндпоинтов, которые идут на бэкенд (остальные отвечают моки).
   * mock: только `auth` (или ничего при VITE_MOCK_AUTH=1); real: `VITE_REAL_API`, по умолчанию `auth`.
   */
  readonly realApi: string;
}

/** Прочитать окружение Vite. */
export function readEnv(): AppEnv {
  const env = import.meta.env;
  return {
    apiMode: env.VITE_API_MODE === 'real' ? 'real' : 'mock',
    defaultMaster: env.VITE_DEFAULT_MASTER || null,
    vapidPublicKey: env.VITE_VAPID_PUBLIC_KEY || null,
    realApi:
      env.VITE_API_MODE === 'real'
        ? (env.VITE_REAL_API ?? 'auth')
        : env.VITE_MOCK_AUTH === '1' || env.VITE_MOCK_AUTH === 'true'
          ? ''
          : 'auth',
  };
}
