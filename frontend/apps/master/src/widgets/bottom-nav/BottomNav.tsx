import { Icon, cx, type IconName } from '@beauty/ui';
import { NavLink } from 'react-router';
import { useInbox } from '../../entities/conversation/queries';
import styles from './BottomNav.module.css';

const ITEMS: Array<{ to: string; label: string; icon: IconName }> = [
  { to: '/schedule', label: 'График', icon: 'calendar' },
  { to: '/chats', label: 'Чаты', icon: 'chat' },
  { to: '/clients', label: 'Клиенты', icon: 'users' },
  { to: '/settings', label: 'Настройки', icon: 'settings' },
];

/** Нижняя навигация: График · Чаты (счётчик «нужны вы») · Поручить · Клиенты · Настройки. */
export function BottomNav() {
  const inbox = useInbox('all', '');
  const needsMe = inbox.data?.counts.needs_me ?? 0;
  const link = (item: (typeof ITEMS)[number]) => (
    <NavLink
      key={item.to}
      to={item.to}
      className={({ isActive }) => cx(styles.item, isActive && styles.active)}
    >
      <Icon name={item.icon} strokeWidth={1.9} />
      {item.label}
      {item.to === '/chats' && needsMe > 0 && (
        <span className={styles.badge} aria-label={`, нужны вы: ${needsMe}`}>
          {needsMe}
        </span>
      )}
    </NavLink>
  );
  return (
    <nav className={styles.nav} aria-label="Разделы">
      {ITEMS.slice(0, 2).map(link)}
      <NavLink to="/assistant" className={styles.item} aria-label="Поручить агенту">
        <span className={styles.fab}>
          <Icon name="mic" size={24} strokeWidth={2} />
        </span>
      </NavLink>
      {ITEMS.slice(2).map(link)}
    </nav>
  );
}
