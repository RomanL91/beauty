import type { ReactNode } from 'react';
import styles from './Notice.module.css';
import { cx } from '../cx';
import { Icon, type IconName } from './Icon';

/** Плашка-пояснение (ИИ-ассистент, безопасность входа, предупреждения). */
export function Notice({
  tone = 'accent',
  icon,
  children,
  role,
  className,
}: {
  readonly tone?: 'accent' | 'muted' | 'warn' | 'ok';
  readonly icon?: IconName;
  readonly children: ReactNode;
  readonly role?: 'status' | 'alert';
  readonly className?: string;
}) {
  return (
    <div className={cx(styles.notice, styles[tone], className)} role={role}>
      {icon && <Icon name={icon} size={tone === 'muted' ? 18 : 20} strokeWidth={1.8} />}
      <div className={styles.body}>{children}</div>
    </div>
  );
}
