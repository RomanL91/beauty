import { AppShell, OfflineBanner } from '@beauty/ui';
import { Outlet } from 'react-router';
import { EventsBridge } from './EventsBridge';

/** Оболочка кабинета: колонка до 480 px, офлайн-полоса, поток событий. */
export function RootLayout() {
  return (
    <AppShell>
      <OfflineBanner />
      <EventsBridge />
      <Outlet />
    </AppShell>
  );
}
