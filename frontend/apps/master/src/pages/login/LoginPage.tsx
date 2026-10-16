import { TelegramLoginPanel, useTelegramLogin } from '@beauty/telegram-login';
import { Navigate, useSearchParams } from 'react-router';
import { useContainer } from '../../shared/lib/container-context';
import { useSession } from '../../shared/lib/use-session';
import styles from './LoginPage.module.css';

/** Только внутренний путь возврата. */
function safeReturn(value: string | null): string {
  return value?.startsWith('/') && !value.startsWith('//') ? value : '/schedule';
}

/** Вход мастера в кабинет — тот же Telegram, что у клиентов. */
export function LoginPage() {
  const [params] = useSearchParams();
  const returnTo = safeReturn(params.get('return'));
  const session = useSession();
  const login = useTelegramLogin(useContainer().auth);

  if (
    login.state.step === 'signed-in' ||
    (session.status === 'authenticated' && login.state.step === 'starting')
  ) {
    return <Navigate to={returnTo} replace />;
  }

  return (
    <main className={styles.page}>
      <div className={styles.intro}>
        <span className={styles.caption}>Кабинет мастера</span>
        <h1 className={styles.h1}>Вход через Telegram</h1>
        <p className={styles.lead}>
          Войдите тем Telegram, к номеру которого привязана ваша страница на beautiful.kz.
        </p>
      </div>
      <TelegramLoginPanel login={login} />
    </main>
  );
}
