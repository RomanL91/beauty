import styles from './OfflineBanner.module.css';
import { Icon } from './Icon';
import { useOnline } from '../hooks/useOnline';

/** Полоса «нет сети» поверх экрана. */
export function OfflineBanner({
  text = 'Нет сети — покажем сохранённое',
}: {
  readonly text?: string;
}) {
  const online = useOnline();
  if (online) return null;
  return (
    <div className={styles.banner} role="status">
      <Icon name="offline" size={16} strokeWidth={2} />
      {text}
    </div>
  );
}
