import type { ReactNode } from 'react';
import styles from './StateView.module.css';
import { Button } from './Button';
import { Icon, type IconName } from './Icon';

/** Пустое состояние / ошибка с действием. */
export function StateView({
  icon = 'chat',
  title,
  text,
  action,
  role,
}: {
  readonly icon?: IconName;
  readonly title: string;
  readonly text?: ReactNode;
  readonly action?: ReactNode;
  readonly role?: 'alert' | 'status';
}) {
  return (
    <div className={styles.state} role={role}>
      <span className={styles.icon}>
        <Icon name={icon} size={26} />
      </span>
      <p className={styles.title}>{title}</p>
      {text && <p className={styles.text}>{text}</p>}
      {action}
    </div>
  );
}

/** Ошибка загрузки с повтором (учитывает офлайн). */
export function ErrorState({
  offline,
  onRetry,
  title,
}: {
  readonly offline: boolean;
  readonly onRetry: () => void;
  readonly title?: string;
}) {
  return (
    <StateView
      role="alert"
      icon={offline ? 'offline' : 'retry'}
      title={title ?? (offline ? 'Нет соединения' : 'Не получилось загрузить')}
      text={
        offline
          ? 'Проверьте интернет — покажем, как только связь вернётся.'
          : 'Попробуйте ещё раз через минуту.'
      }
      action={
        <Button variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      }
    />
  );
}
