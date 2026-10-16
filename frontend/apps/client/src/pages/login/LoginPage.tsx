import { TelegramLoginPanel, useTelegramLogin } from '@beauty/telegram-login';
import { Icon, iconButtonClass } from '@beauty/ui';
import { Link, Navigate, useSearchParams } from 'react-router';
import { useMasterPage } from '../../entities/master/queries';
import { useSession } from '../../entities/session/use-session';
import { safeReturn } from '../../shared/lib/booking-intent';
import { useContainer } from '../../shared/lib/container-context';
import styles from './LoginPage.module.css';

/** Экран «Вход через Telegram» (макет ClientLogin). */
export function LoginPage() {
  const [params] = useSearchParams();
  const returnTo = safeReturn(params.get('return'));
  const session = useSession();
  const master = useMasterPage();
  const login = useTelegramLogin(useContainer().auth);
  const { state } = login;

  if (
    state.step === 'signed-in' ||
    (session.status === 'authenticated' && state.step === 'starting')
  ) {
    return <Navigate to={returnTo} replace />;
  }

  const names = master.data?.name_forms;
  const booking = returnTo.includes('book=1');
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link
          to={returnTo.startsWith('/chat') ? '/' : returnTo}
          className={iconButtonClass()}
          aria-label="Назад"
        >
          <Icon name="back" strokeWidth={2} />
        </Link>
        <span className={styles.caption}>
          {booking && names ? `Запись к ${names.dative}` : 'Вход'}
        </span>
      </header>

      <div className={styles.intro}>
        <h1 className={styles.h1}>Вход через Telegram</h1>
        <p className={styles.lead}>
          Один раз — и {names?.nominative ?? 'мастер'} будет узнавать вас на любой странице
          beautiful.kz.
        </p>
      </div>

      <TelegramLoginPanel login={login} />

      <div className={styles.bottom}>
        <Link to={returnTo.startsWith('/chat') ? '/' : returnTo} className={styles.cancel}>
          Отменить вход
        </Link>
      </div>
    </main>
  );
}
