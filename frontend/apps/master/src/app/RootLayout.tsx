import { ApiError } from '@beauty/api';
import { AppShell, Button, FeedSkeleton, OfflineBanner, StateView } from '@beauty/ui';
import { Navigate, Outlet, useLocation } from 'react-router';
import { useProfile } from '../entities/schedule/queries';
import { useContainer } from '../shared/lib/container-context';
import { useSession } from '../shared/lib/use-session';
import { EventsBridge } from './EventsBridge';

/**
 * Оболочка кабинета: колонка до 480 px, офлайн-полоса, поток событий.
 *
 * Кабинет только для входа: без сессии — экран входа (с возвратом), учётная
 * запись без страницы мастера — объяснение и выход.
 */
export function RootLayout() {
  const session = useSession();
  const location = useLocation();
  const profile = useProfile(session.status === 'authenticated');

  if (session.status === 'unknown') {
    return (
      <AppShell>
        <FeedSkeleton />
      </AppShell>
    );
  }
  if (session.status === 'anonymous') {
    const back = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?return=${encodeURIComponent(back)}`} replace />;
  }
  if (profile.error instanceof ApiError && profile.error.code === 'not_a_master') {
    return (
      <AppShell>
        <NotMaster />
      </AppShell>
    );
  }
  return (
    <AppShell>
      <OfflineBanner />
      <EventsBridge />
      <Outlet />
    </AppShell>
  );
}

/** Вход выполнен, но к этому Telegram не привязана страница мастера. */
function NotMaster() {
  const { auth } = useContainer();
  return (
    <StateView
      role="alert"
      icon="lock"
      title="Это не кабинет мастера"
      text="К этому номеру Telegram не привязана страница мастера. Войдите номером, который указан у вашей страницы, или напишите в поддержку beautiful.kz."
      action={
        <Button variant="secondary" onClick={() => void auth.logout()}>
          Войти другим аккаунтом
        </Button>
      }
    />
  );
}
