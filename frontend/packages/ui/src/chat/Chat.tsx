import { useEffect, useRef, useState, type ReactNode } from 'react';
import styles from './Chat.module.css';
import { cx } from '../cx';
import { formatDuration } from '../format';
import { Icon } from '../components/Icon';
import { Waveform } from '../components/Waveform';

/** Сторона пузыря: свои сообщения справа, собеседник слева. */
export type BubbleSide = 'out' | 'in';
/** Заливка пузыря: `accent` — свои у клиента, `surface` — собеседник, `soft` — агент у мастера. */
export type BubbleTone = 'accent' | 'surface' | 'soft';

/** Строка ленты: пузырь и подписи под ним. */
export function MessageRow({
  side,
  wide = false,
  children,
}: {
  readonly side: BubbleSide;
  readonly wide?: boolean;
  readonly children: ReactNode;
}) {
  return <div className={cx(styles.row, styles[side], wide && styles.wide)}>{children}</div>;
}

/** Пузырь сообщения. */
export function Bubble({
  tone,
  layout = 'text',
  pending = false,
  children,
}: {
  readonly tone: BubbleTone;
  /** `text` — текст, `stack` — столбик блоков, `flush` — карточка без отступов. */
  readonly layout?: 'text' | 'stack' | 'flush';
  readonly pending?: boolean;
  readonly children: ReactNode;
}) {
  return (
    <div
      className={cx(
        styles.bubble,
        styles[tone],
        layout === 'stack' && styles.stack,
        layout === 'flush' && styles.flush,
        pending && styles.pending,
      )}
    >
      {children}
    </div>
  );
}

/** Подпись под пузырём: «✶ Ответ ИИ · 14:02». */
export function BubbleMeta({
  ai = false,
  children,
}: {
  readonly ai?: boolean;
  readonly children: ReactNode;
}) {
  return (
    <span className={styles.meta}>
      {ai && <Icon name="sparkle" size={14} strokeWidth={2} />}
      {children}
    </span>
  );
}

/** Подпись над пузырём (у мастера: «Агент · 14:02»). */
export function BubbleLabel({ children }: { readonly children: ReactNode }) {
  return <span className={styles.label}>{children}</span>;
}

/** Не отправлено — повторить. */
export function FailedBadge({ onRetry }: { readonly onRetry: () => void }) {
  return (
    <button type="button" className={styles.failed} onClick={onRetry}>
      <Icon name="retry" size={14} strokeWidth={2.2} />
      Не отправлено · Повторить
    </button>
  );
}

/** Блок «Источники» внутри пузыря. */
export function Sources({
  items,
}: {
  readonly items: ReadonlyArray<{ title: string; url: string }>;
}) {
  if (items.length === 0) return null;
  return (
    <div className={styles.sources}>
      <span className={styles.sourcesTitle}>Источники</span>
      {items.map((s) => (
        <a key={s.url + s.title} href={s.url} target="_blank" rel="noopener noreferrer">
          {s.title}
        </a>
      ))}
    </div>
  );
}

/** Разделитель дня. */
export function DaySeparator({ children }: { readonly children: ReactNode }) {
  return <div className={styles.day}>{children}</div>;
}

/** Системное сообщение по центру. */
export function SystemPill({
  tone,
  children,
}: {
  readonly tone: 'success' | 'info' | 'warning';
  readonly children: ReactNode;
}) {
  return (
    <div className={cx(styles.system, styles[tone])} role="status">
      {tone === 'success' && <Icon name="check" size={16} strokeWidth={2} />}
      {children}
    </div>
  );
}

/** Кнопки выбора окна из slot_offer. */
export function SlotButtons({
  slots,
  selected,
  disabled,
  label,
  onPick,
}: {
  readonly slots: ReadonlyArray<{ start: string }>;
  readonly selected: string | null;
  readonly disabled: boolean;
  readonly label: (start: string) => string;
  readonly onPick: (start: string) => void;
}) {
  return (
    <div className={styles.slots} role="group" aria-label="Свободное время">
      {slots.map((s) => (
        <button
          key={s.start}
          type="button"
          className={styles.slot}
          aria-pressed={selected === s.start}
          disabled={disabled || selected !== null}
          onClick={() => onPick(s.start)}
        >
          {label(s.start)}
        </button>
      ))}
    </div>
  );
}

/** Общий плеер: в каждый момент играет одно голосовое. */
let current: HTMLAudioElement | null = null;

/** Голосовое: кнопка воспроизведения, волна, длительность и расшифровка. */
export function VoicePlayer({
  src,
  duration,
  transcript,
  tone,
}: {
  readonly src: string;
  readonly duration: number;
  readonly transcript?: string | null;
  readonly tone: BubbleTone;
}) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(
    () => () => {
      audio.current?.pause();
    },
    [],
  );

  const toggle = () => {
    if (!audio.current) {
      const el = new Audio(src);
      el.ontimeupdate = () => setProgress(el.duration ? el.currentTime / el.duration : 0);
      el.onended = () => {
        setPlaying(false);
        setProgress(0);
      };
      el.onpause = () => setPlaying(false);
      el.onplay = () => setPlaying(true);
      audio.current = el;
    }
    const el = audio.current;
    if (playing) {
      el.pause();
      return;
    }
    if (current && current !== el) current.pause();
    current = el;
    void el.play().catch(() => setPlaying(false));
  };

  const accent = tone === 'accent';
  return (
    <div className={styles.voice}>
      <div className={styles.voiceRow}>
        <button
          type="button"
          className={cx(styles.play, accent ? styles.playOnAccent : styles.playOnSurface)}
          onClick={toggle}
          aria-label={playing ? 'Пауза' : 'Воспроизвести голосовое'}
        >
          <Icon name={playing ? 'pause' : 'play'} size={14} />
        </button>
        <Waveform
          color={accent ? 'var(--c-wave)' : 'var(--c-dashed)'}
          playedColor={accent ? '#ffffff' : 'var(--c-accent)'}
          progress={progress}
        />
        <span className={styles.duration}>{formatDuration(duration)}</span>
      </div>
      {transcript && (
        <span
          className={cx(
            styles.transcript,
            accent ? styles.transcriptOnAccent : styles.transcriptOnSurface,
          )}
        >
          «{transcript}»
        </span>
      )}
    </div>
  );
}
