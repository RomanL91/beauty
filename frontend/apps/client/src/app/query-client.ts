import { QueryClient } from '@tanstack/react-query';

/** Клиент TanStack Query: данные — сеть в приоритете, кэш на офлайн. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 1, networkMode: 'offlineFirst', refetchOnWindowFocus: true },
      mutations: { networkMode: 'offlineFirst', retry: 0 },
    },
  });
}
