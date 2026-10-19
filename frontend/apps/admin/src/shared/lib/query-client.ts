import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { isUnauthorized, sessionKey } from './session';

/** Клиент запросов: сессия кончилась (401) — панель сама уходит на вход. */
export function createQueryClient(): QueryClient {
  const expire = (error: unknown) => {
    if (isUnauthorized(error)) client.setQueryData(sessionKey, null);
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: expire }),
    mutationCache: new MutationCache({ onError: expire }),
    defaultOptions: {
      queries: {
        retry: (count, error) => !isUnauthorized(error) && count < 1,
        refetchOnWindowFocus: true,
      },
      mutations: { retry: 0 },
    },
  });
  return client;
}
