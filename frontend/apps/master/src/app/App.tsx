import { useEffect, useState } from 'react';
import { RouterProvider } from 'react-router';
import type { MasterContainer } from './container';
import { AppProviders } from './providers';
import { createRouter } from './router';

/** Кабинет мастера. */
export function App({ container }: { readonly container: MasterContainer }) {
  const [router] = useState(createRouter);
  useEffect(() => {
    // Сессия по refresh-cookie (или заглушка в моках); до ответа — скелетон.
    void container.auth.restoreSession();
  }, [container]);
  return (
    <AppProviders container={container}>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
