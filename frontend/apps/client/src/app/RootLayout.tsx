import { AppShell, OfflineBanner, StateView, useToast } from '@beauty/ui';
import { useEffect, useRef } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { useSession } from '../entities/session/use-session';
import { loginHref } from '../shared/lib/booking-intent';
import { useContainer } from '../shared/lib/container-context';

/** Оболочка: колонка 480 px, полоса офлайна, реакция на конец сессии. */
export function RootLayout() {
  const { masterSlug } = useContainer();
  const session = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const wasAuthenticated = useRef(false);

  useEffect(() => {
    if (session.status === 'authenticated') {
      wasAuthenticated.current = true;
      return;
    }
    if (session.status !== 'anonymous' || !wasAuthenticated.current) return;
    wasAuthenticated.current = false;
    if (session.reason === 'expired' || session.reason === 'reuse') {
      toast({ text: 'Сессия закончилась — войдите снова' });
      if (location.pathname !== '/' && location.pathname !== '/login') {
        void navigate(loginHref(location.pathname + location.search), { replace: true });
      }
    }
  }, [session, location, navigate, toast]);

  return (
    <AppShell>
      <OfflineBanner />
      {masterSlug ? (
        <Outlet />
      ) : (
        <StateView
          icon="user"
          title="Страница не найдена"
          text="Проверьте адрес: у каждого мастера свой поддомен beautiful.kz."
        />
      )}
    </AppShell>
  );
}
