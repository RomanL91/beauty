import { formatNumber } from '../shared/lib/format';
import styles from './StatTile.module.css';

/** Цифра-итог с подписью. */
export function StatTile({
  label,
  value,
  hint,
}: {
  readonly label: string;
  readonly value: number;
  readonly hint?: string;
}) {
  return (
    <div className={styles.tile}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{formatNumber(value)}</span>
      {hint && <span className={styles.hint}>{hint}</span>}
    </div>
  );
}
