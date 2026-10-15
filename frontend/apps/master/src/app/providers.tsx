import { ToastProvider } from '@beauty/ui';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { ContainerContext } from '../shared/lib/container-context';
import { EventHubContext, MasterEventHub } from '../shared/lib/events';
import type { MasterContainer } from './container';
import { createQueryClient } from './query-client';

/** Корневые провайдеры кабинета. */
export function AppProviders({
  container,
  queryClient,
  children,
}: {
  readonly container: MasterContainer;
  readonly queryClient?: QueryClient;
  readonly children: ReactNode;
}) {
  const [client] = useState(() => queryClient ?? createQueryClient());
  const [hub] = useState(() => new MasterEventHub());
  return (
    <ContainerContext.Provider value={container}>
      <QueryClientProvider client={client}>
        <EventHubContext.Provider value={hub}>
          <ToastProvider>{children}</ToastProvider>
        </EventHubContext.Provider>
      </QueryClientProvider>
    </ContainerContext.Provider>
  );
}
