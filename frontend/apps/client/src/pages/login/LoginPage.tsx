import { formatRemainingClock, remaining } from '@beauty/api';
import {
  Button,
  Icon,
  Notice,
  Skeleton,
  buttonClass,
  cx,
  iconButtonClass,
  useNow,
} from '@beauty/ui';
import { useEffect } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router';
import { useMasterPage } from '../../entities/master/queries';
import { useSession } from '../../entities/session/use-session';
import { useTelegramLogin, type LoginState } from '../../features/auth-telegram/use-telegram-login';
import { safeReturn } from '../../shared/lib/booking-intent';
import styles from './LoginPage.module.css';

/** Экран «Вход через Telegram» (макет ClientLogin). */
export function LoginPage() {
  const [params] = useSearchParams();
  const returnTo = safeReturn(params.get('return'));
  const session = useSession();
  const master = useMasterPage();
  const { state, restart, expire } = useTelegramLogin();
  const now = useNow(1000, state.step === 'waiting');

  const left = state.step === 'waiting' ? remaining(state.challenge.expires_at, now) : null;
  useEffect(() => {
    if (left?.expired) expire();
  }, [left?.expired, expire]);

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

      <ol className={styles.steps}>
        {[
          'Откройте бота кнопкой ниже',
          'Нажмите в боте «Поделиться контактом»',
          'Выберите в боте этот код',
        ].map((text, i) => (
          <li key={text} className={styles.step}>
            <span className={styles.num} aria-hidden="true">
              {i + 1}
            </span>
            <span className={styles.stepText}>{text}</span>
          </li>
        ))}
      </ol>

      <CodeCard
        state={state}
        clock={left ? formatRemainingClock(left) : null}
        onRestart={restart}
      />

      {state.step === 'waiting' || state.step === 'exchanging' ? (
        <a
          href={state.challenge.deep_link}
          target="_blank"
          rel="noopener noreferrer"
          className={buttonClass({ variant: 'telegram', size: 'xl', block: true })}
        >
          <Icon name="telegram" size={20} strokeWidth={2} />
          Открыть Telegram
        </a>
      ) : (
        <span
          className={buttonClass({ variant: 'telegram', size: 'xl', block: true })}
          aria-disabled="true"
        >
          <Icon name="telegram" size={20} strokeWidth={2} />
          Открыть Telegram
        </span>
      )}

      <Notice tone="muted" icon="lock">
        Если бот показывает другие цифры — не нажимайте ничего: эту ссылку открыли не вы. Переписку
        в Telegram мы не видим.
      </Notice>

      <div className={styles.bottom}>
        <Link to={returnTo.startsWith('/chat') ? '/' : returnTo} className={styles.cancel}>
          Отменить вход
        </Link>
      </div>
    </main>
  );
}

const STATUS_TEXT = {
  pending: 'Ждём подтверждения в Telegram',
  claimed: 'Бот открыт — выберите в нём этот код',
  confirmed: 'Код подтверждён — поделитесь контактом',
} as const;

function CodeCard({
  state,
  clock,
  onRestart,
}: {
  readonly state: LoginState;
  readonly clock: string | null;
  readonly onRestart: () => void;
}) {
  if (state.step === 'starting') {
    return (
      <div className={styles.codeCard} aria-busy="true">
        <span className={styles.codeLabel}>Код для бота</span>
        <Skeleton width={110} height={72} radius={14} />
        <Skeleton width={220} height={16} />
      </div>
    );
  }
  if (state.step === 'start-failed') {
    return (
      <div className={styles.codeCard} role="alert">
        <span className={styles.codeLabel}>Код для бота</span>
        <span className={styles.status}>
          <span className={cx(styles.dot, styles.dotBad)} />
          {state.offline ? 'Нет соединения — проверьте интернет' : 'Не удалось начать вход'}
        </span>
        <Button variant="secondary" onClick={onRestart}>
          Попробовать снова
        </Button>
      </div>
    );
  }
  if (state.step === 'signed-in') return null;

  const code = state.challenge.confirmation_code;
  if (state.step === 'failed') {
    const text =
      state.reason === 'rejected'
        ? 'В боте выбран другой код — вход отменён'
        : state.reason === 'expired'
          ? 'Время вышло'
          : 'Не удалось завершить вход';
    return (
      <div className={styles.codeCard} role="alert">
        <span className={styles.codeLabel}>Код для бота</span>
        <span className={styles.code} style={{ color: 'var(--c-text-disabled)' }}>
          {code}
        </span>
        <span className={styles.status}>
          <span className={cx(styles.dot, styles.dotBad)} />
          {text}
        </span>
        <Button onClick={onRestart}>Получить новый код</Button>
      </div>
    );
  }

  const exchanging = state.step === 'exchanging';
  return (
    <div className={styles.codeCard}>
      <span className={styles.codeLabel} id="code-label">
        Код для бота
      </span>
      <span className={styles.code} aria-describedby="code-label">
        {code}
      </span>
      <span className={styles.status} role="status" aria-live="polite">
        <span
          className={cx(styles.dot, (exchanging || state.status === 'confirmed') && styles.dotOk)}
        />
        {exchanging
          ? 'Готово — входим…'
          : `${STATUS_TEXT[state.status as keyof typeof STATUS_TEXT] ?? STATUS_TEXT.pending}${clock ? ` · ${clock}` : ''}`}
      </span>
      {state.step === 'waiting' && state.stream === 'reconnecting' && (
        <span className={styles.reconnect}>Связь прервалась — проверяем статус вручную</span>
      )}
    </div>
  );
}
