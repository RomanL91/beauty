import type { FeedItem, MessageOf } from '@beauty/api';
import {
  Bubble,
  BubbleMeta,
  FailedBadge,
  Icon,
  MessageRow,
  VoicePlayer,
  cx,
  formatDuration,
  formatTime,
} from '@beauty/ui';
import type { ReactNode } from 'react';
import styles from './Assistant.module.css';

/** Сообщение ленты поручений. */
export function AssistantMessageView({
  item,
  timeZone,
  onChoose,
  onRetry,
  choosing,
}: {
  readonly item: FeedItem;
  readonly timeZone: string;
  readonly onChoose: (choice: MessageOf<'choice'>, optionId: string) => void;
  readonly onRetry: (clientId: string) => void;
  /** Ответ на какой вопрос сейчас отправляется. */
  readonly choosing: string | null;
}) {
  const { message, delivery } = item;
  const mine = message.author === 'master';
  const failed =
    delivery === 'failed' ? <FailedBadge onRetry={() => onRetry(message.client_id ?? '')} /> : null;

  switch (message.kind) {
    case 'voice':
      return (
        <MessageRow side={mine ? 'out' : 'in'} wide>
          <Bubble
            tone={mine ? 'accent' : 'surface'}
            layout="stack"
            pending={delivery === 'pending'}
          >
            <span className={styles.voiceLabel}>
              <Icon name="mic" size={14} strokeWidth={2} />
              Голосовое · {formatDuration(message.duration)}
            </span>
            {message.transcript ? (
              <span>«{message.transcript}»</span>
            ) : (
              <VoicePlayer
                src={message.audio_url}
                duration={message.duration}
                tone={mine ? 'accent' : 'surface'}
              />
            )}
          </Bubble>
          {failed}
        </MessageRow>
      );
    case 'text':
      return (
        <MessageRow side={mine ? 'out' : 'in'}>
          <Bubble tone={mine ? 'accent' : 'surface'} pending={delivery === 'pending'}>
            {message.text}
          </Bubble>
          {failed ?? (!mine && <BubbleMeta>{formatTime(message.created_at, timeZone)}</BubbleMeta>)}
        </MessageRow>
      );
    case 'choice':
      return <Choice message={message} busy={choosing === message.choice_id} onChoose={onChoose} />;
    case 'task_progress':
      return <Progress message={message} />;
    case 'system':
      return (
        <MessageRow side="in">
          <Bubble tone="surface">{message.text}</Bubble>
        </MessageRow>
      );
    default:
      return null;
  }
}

/** `**жирный**` в тексте агента. */
function rich(text: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, i) =>
      part.startsWith('**') && part.endsWith('**') ? <b key={i}>{part.slice(2, -2)}</b> : part,
    );
}

function Choice({
  message,
  busy,
  onChoose,
}: {
  readonly message: MessageOf<'choice'>;
  readonly busy: boolean;
  readonly onChoose: (choice: MessageOf<'choice'>, optionId: string) => void;
}) {
  const answered = message.selected_option_id !== null;
  const long = message.options.some((o) => o.label.length > 22) || Boolean(message.detail);
  if (!long) {
    return (
      <MessageRow side="in">
        <Bubble tone="surface" layout="stack">
          <span>{rich(message.text)}</span>
          <div className={styles.choiceRow} role="group" aria-label="Варианты">
            {message.options.map((o) => (
              <button
                key={o.id}
                type="button"
                className={styles.option}
                aria-pressed={message.selected_option_id === o.id}
                disabled={answered || busy}
                onClick={() => onChoose(message, o.id)}
              >
                {o.label}
              </button>
            ))}
          </div>
        </Bubble>
      </MessageRow>
    );
  }
  return (
    <MessageRow side="in" wide>
      <Bubble tone="surface" layout="flush">
        <div className={styles.card}>
          <div className={styles.cardText}>
            <span>{rich(message.text)}</span>
            {message.detail && <span className={styles.detail}>{message.detail}</span>}
          </div>
          <div className={styles.options} role="group" aria-label="Варианты">
            {message.options.map((o) => (
              <button
                key={o.id}
                type="button"
                className={cx(styles.optionRow, o.tone === 'muted' && styles.muted)}
                aria-pressed={message.selected_option_id === o.id}
                disabled={answered || busy}
                onClick={() => onChoose(message, o.id)}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
      </Bubble>
    </MessageRow>
  );
}

const STEP_LABEL = {
  done: 'готово',
  waiting: 'в процессе',
  pending: 'впереди',
  failed: 'не получилось',
} as const;

function Progress({ message }: { readonly message: MessageOf<'task_progress'> }) {
  return (
    <MessageRow side="in" wide>
      <Bubble tone="surface" layout="stack">
        <div className={styles.progress}>
          <span className={styles.progressTitle}>{message.title}</span>
          <ol className={styles.steps} aria-live="polite">
            {message.steps.map((s) => (
              <li
                key={s.id}
                className={cx(styles.step, s.state === 'pending' && styles.stepPending)}
              >
                <span
                  className={cx(styles.stepIcon, styles[s.state])}
                  aria-label={STEP_LABEL[s.state]}
                  role="img"
                >
                  {s.state === 'done' && <Icon name="check" size={14} strokeWidth={2.4} />}
                  {s.state === 'waiting' && <Icon name="pending" size={14} strokeWidth={2.2} />}
                  {s.state === 'failed' && <Icon name="close" size={12} strokeWidth={2.4} />}
                </span>
                {s.label}
              </li>
            ))}
          </ol>
          {message.footnote && <span className={styles.footnote}>{message.footnote}</span>}
        </div>
      </Bubble>
    </MessageRow>
  );
}
