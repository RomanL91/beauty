import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import { useSession } from '../entities/session/use-session';
import { loginHref } from '../shared/lib/booking-intent';

/** Экран только для вошедших: пока сессия восстанавливается — заглушка. */
export function RequireSession({
  fallback,
  children,
}: {
  readonly fallback: ReactNode;
  readonly children: ReactNode;
}) {
  const session = useSession();
  const location = useLocation();
  if (session.status === 'unknown') return fallback;
  if (session.status === 'anonymous') {
    return <Navigate to={loginHref(location.pathname + location.search)} replace />;
  }
  return children;
}
