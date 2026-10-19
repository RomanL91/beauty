import { Button, Icon, OfflineBanner, cx, type IconName } from '@beauty/ui';
import { Navigate, NavLink, Outlet, useLocation } from 'react-router';
import { isUnauthorized, useLogout, useSession } from '../shared/lib/session';
import styles from './Layout.module.css';

const NAV: Array<{ to: string; label: string; icon: IconName }> = [
  { to: '/', label: 'Сводка', icon: 'home' },
  { to: '/masters', label: 'Мастера', icon: 'user' },
  { to: '/clients', label: 'Клиенты', icon: 'users' },
  { to: '/agent', label: 'ИИ-администратор', icon: 'sparkle' },
  { to: '/admins', label: 'Администраторы', icon: 'lock' },
  { to: '/audit', label: 'Журнал', icon: 'clock' },
  { to: '/system', label: 'Система', icon: 'settings' },
];

/** Оболочка панели: меню слева (на телефоне — сверху), без сессии — экран входа. */
export function Layout() {
  const session = useSession();
  const logout = useLogout();
  const location = useLocation();
  if (session.isPending) return <div className={styles.loading} aria-busy="true" />;
  if (!session.data || isUnauthorized(session.error)) {
    const back = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?return=${encodeURIComponent(back)}`} replace />;
  }
  const admin = session.data.admin;
  return (
    <div className={styles.layout}>
      <aside className={styles.side}>
        <div className={styles.brand}>
          <span className={styles.logo}>b</span>
          <span>
            <strong>beautiful.kz</strong>
            <span className={styles.caption}>Панель хозяина</span>
          </span>
        </div>
        <nav aria-label="Разделы" className={styles.nav}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              aria-label={item.label}
              title={item.label}
              className={({ isActive }) => cx(styles.link, isActive && styles.active)}
            >
              <Icon name={item.icon} size={20} strokeWidth={1.8} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className={styles.me}>
          <span className={styles.meName}>{admin.display_name}</span>
          <span className={styles.caption}>{admin.login}</span>
          <Button variant="ghost" onClick={() => logout.mutate()} disabled={logout.isPending}>
            Выйти
          </Button>
        </div>
      </aside>
      <main className={styles.main}>
        <OfflineBanner />
        <Outlet />
      </main>
    </div>
  );
}
