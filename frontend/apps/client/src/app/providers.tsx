import { ToastProvider } from '@beauty/ui';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { ContainerContext } from '../shared/lib/container-context';
import type { ClientContainer } from './container';
import { createQueryClient } from './query-client';

/** Корневые провайдеры: контейнер зависимостей, кэш запросов, уведомления. */
export function AppProviders({
  container,
  queryClient,
  children,
}: {
  readonly container: ClientContainer;
  readonly queryClient?: QueryClient;
  readonly children: ReactNode;
}) {
  const [client] = useState(() => queryClient ?? createQueryClient());
  return (
    <ContainerContext.Provider value={container}>
      <QueryClientProvider client={client}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    </ContainerContext.Provider>
  );
}
