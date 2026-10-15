import { useEffect, useState } from 'react';
import { RouterProvider } from 'react-router';
import type { ClientContainer } from './container';
import { AppProviders } from './providers';
import { createRouter } from './router';

/** Приложение клиента. */
export function App({ container }: { readonly container: ClientContainer }) {
  const [router] = useState(createRouter);
  useEffect(() => {
    // Восстановить сессию по refresh-cookie; страница мастера публичная и не ждёт.
    void container.auth.restoreSession();
  }, [container]);
  return (
    <AppProviders container={container}>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
