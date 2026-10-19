import { ToastProvider } from '@beauty/ui';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { RouterProvider } from 'react-router';
import { ContainerContext, type AdminContainer } from '../shared/lib/container';
import { createQueryClient } from '../shared/lib/query-client';
import { createRouter } from './router';

/** Админ-панель хозяина сервиса. */
export function App({
  container,
  queryClient,
}: {
  readonly container: AdminContainer;
  readonly queryClient?: QueryClient;
}) {
  const [router] = useState(createRouter);
  const [client] = useState(() => queryClient ?? createQueryClient());
  return (
    <ContainerContext.Provider value={container}>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </QueryClientProvider>
    </ContainerContext.Provider>
  );
}
