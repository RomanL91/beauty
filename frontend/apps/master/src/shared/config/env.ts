/** Настройки сборки кабинета мастера (из `VITE_*`). */
export interface AppEnv {
  readonly apiMode: 'mock' | 'real';
  readonly vapidPublicKey: string | null;
}

/** Прочитать окружение Vite. */
export function readEnv(): AppEnv {
  const env = import.meta.env;
  return {
    apiMode: env.VITE_API_MODE === 'real' ? 'real' : 'mock',
    vapidPublicKey: env.VITE_VAPID_PUBLIC_KEY || null,
  };
}
