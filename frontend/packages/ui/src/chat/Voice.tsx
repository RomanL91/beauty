import { cx } from '../cx';
import { formatDuration } from '../format';
import { useNow } from '../hooks/useNow';
import type { VoiceClip } from '../hooks/useVoiceRecorder';
import { IconButton } from '../components/Button';
import { Icon } from '../components/Icon';
import { VoicePlayer } from './Chat';
import styles from './Voice.module.css';

/** Полоса «идёт запись»: таймер, лимит и подсказка об отмене свайпом. */
export function VoiceRecordingBar({
  startedAt,
  maxSeconds,
  cancelArmed,
}: {
  readonly startedAt: number;
  readonly maxSeconds: number;
  readonly cancelArmed: boolean;
}) {
  const now = useNow(250);
  const seconds = Math.min(maxSeconds, Math.max(0, (now - startedAt) / 1000));
  return (
    <div className={cx(styles.bar, cancelArmed && styles.armed)} role="status" aria-live="off">
      <span className={styles.dot} aria-hidden="true" />
      <span className={styles.time}>
        {formatDuration(seconds)}
        <span style={{ color: 'var(--c-text-muted)', fontWeight: 600 }}>
          {' '}
          / {formatDuration(maxSeconds)}
        </span>
      </span>
      <span className={styles.hint}>{cancelArmed ? 'Отпустите — удалим' : '← влево — отмена'}</span>
    </div>
  );
}

/** Превью записанного голосового: прослушать, удалить или отправить. */
export function VoicePreviewBar({
  clip,
  onDiscard,
  onSend,
}: {
  readonly clip: VoiceClip;
  readonly onDiscard: () => void;
  readonly onSend: () => void;
}) {
  return (
    <>
      <div className={cx(styles.bar, styles.preview)}>
        <VoicePlayer src={clip.url} duration={clip.duration} tone="surface" />
        <IconButton label="Удалить запись" className={styles.discard} onClick={onDiscard}>
          <Icon name="trash" size={20} />
        </IconButton>
      </div>
      <IconButton label="Отправить голосовое" look="accent" onClick={onSend}>
        <Icon name="send" size={20} strokeWidth={2} />
      </IconButton>
    </>
  );
}
