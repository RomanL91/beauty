/** Настройки сборки кабинета мастера (из `VITE_*`). */
export interface AppEnv {
  readonly apiMode: 'mock' | 'real';
  readonly vapidPublicKey: string | null;
  /** Группы эндпоинтов, которые идут на бэкенд (остальные отвечают моки в странице). */
  readonly realApi: string;
  /**
   * Вход мастера — заглушка с мгновенной сессией: так работают моки и e2e
   * (вход не на бэкенде). В реальной сборке — вход через Telegram.
   */
  readonly stubAuth: boolean;
  /**
   * Поручения ещё не на бэкенде, а поток событий кабинета уже на нём: ответы
   * мок-агента не дойдут — экран поручений показывает «появится вместе с агентом».
   */
  readonly assistantPending: boolean;
}

/** Прочитать окружение Vite. */
export function readEnv(): AppEnv {
  const env = import.meta.env;
  const realApi = env.VITE_API_MODE === 'real' ? (env.VITE_REAL_API ?? '') : '';
  const groups = new Set(
    realApi
      .split(',')
      .map((group) => group.trim())
      .filter(Boolean),
  );
  const all = groups.has('all');
  return {
    apiMode: env.VITE_API_MODE === 'real' ? 'real' : 'mock',
    vapidPublicKey: env.VITE_VAPID_PUBLIC_KEY || null,
    realApi,
    stubAuth: !all && !groups.has('auth'),
    assistantPending: !all && groups.has('master') && !groups.has('assistant'),
  };
}
