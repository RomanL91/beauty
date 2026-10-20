import type { MessageOf, OutgoingDraft } from '@beauty/api';
import {
  ChatFeed,
  ErrorState,
  FeedSkeleton,
  HoldToRecord,
  Icon,
  VoicePreviewBar,
  VoiceRecordingBar,
  iconButtonClass,
  useOnline,
  useToast,
  useVoiceRecorder,
  visuallyHiddenStyle,
} from '@beauty/ui';
import { useMutation } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { useProfile } from '../../entities/schedule/queries';
import { AssistantMessageView } from '../../features/assistant-tasks/AssistantMessageView';
import { newClientId } from '../../shared/lib/client-id';
import { useContainer } from '../../shared/lib/container-context';
import { DEFAULT_TZ } from '../../shared/lib/dates';
import { localMessage, useLiveFeed } from '../../shared/lib/use-live-feed';
import styles from './AssistantPage.module.css';

const QUICK = [
  'Расскажу, как я работаю',
  'Что у меня завтра?',
  'Закрой воскресенье',
  'Обед на 14:00',
];

const RECORDER_ERRORS = {
  denied: 'Нет доступа к микрофону — разрешите его в настройках браузера',
  unsupported: 'Браузер не умеет записывать голос — дайте поручение текстом',
  'too-short': 'Удерживайте кнопку, пока говорите',
  failed: 'Не получилось включить микрофон',
} as const;

/** Экран «Поручения» (макет MasterAssistant). */
export function AssistantPage() {
  const { assistant } = useContainer();
  const tz = useProfile().data?.timezone ?? DEFAULT_TZ;
  const online = useOnline();
  const toast = useToast();

  const source = useMemo(
    () => ({
      channel: null,
      load: (cursor: { before?: string; limit?: number }) => assistant.listMessages(cursor),
      deliver: (clientId: string, draft: OutgoingDraft) =>
        draft.kind === 'voice'
          ? assistant.sendVoice({ clientId, audio: draft.audio, duration: draft.duration })
          : assistant.sendText({
              kind: 'text',
              client_id: clientId,
              text: draft.kind === 'text' ? draft.text : '',
            }),
    }),
    [assistant],
  );
  const live = useLiveFeed(source);

  const choose = useMutation({
    mutationFn: ({ choice, optionId }: { choice: MessageOf<'choice'>; optionId: string }) =>
      assistant.choose(choice.choice_id, optionId),
    onMutate: ({ choice, optionId }) =>
      live.applyUpdate({ ...choice, selected_option_id: optionId }),
    onSuccess: (message) => live.applyUpdate(message),
    onError: (_e, { choice }) => {
      live.applyUpdate(choice);
      toast({ text: 'Не получилось передать выбор — попробуйте ещё раз' });
    },
  });

  const sendText = useCallback(
    (text: string) => {
      const clientId = newClientId();
      void live.send(
        clientId,
        { kind: 'text', text },
        localMessage(clientId, { kind: 'text', text }),
      );
    },
    [live],
  );

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link to="/schedule" className={iconButtonClass()} aria-label="К графику">
          <Icon name="back" strokeWidth={2} />
        </Link>
        <div className={styles.titles}>
          <h1 className={styles.title}>Поручения</h1>
          <span className={styles.subtitle}>Ваш администратор · видите только вы</span>
        </div>
      </header>

      <div className={styles.body}>
        {live.initial.status === 'error' ? (
          <ErrorState offline={!online} onRetry={live.retryInitial} />
        ) : live.initial.status === 'loading' ? (
          <FeedSkeleton />
        ) : (
          <ChatFeed
            label="Поручения агенту"
            feed={live.feed}
            timeZone={tz}
            older={live.older}
            onLoadOlder={() => void live.loadOlder()}
            renderItem={(index) => {
              const item = live.feed.items[index];
              return item ? (
                <AssistantMessageView
                  item={item}
                  timeZone={tz}
                  onRetry={live.retry}
                  choosing={choose.isPending ? (choose.variables?.choice.choice_id ?? null) : null}
                  onChoose={(choice, optionId) => choose.mutate({ choice, optionId })}
                />
              ) : null;
            }}
          />
        )}
      </div>

      <TaskComposer
        onText={sendText}
        onVoice={(clip) => {
          const clientId = newClientId();
          void live.send(
            clientId,
            { kind: 'voice', audio: clip.blob, duration: clip.duration },
            localMessage(clientId, {
              kind: 'voice',
              audio_url: clip.url,
              duration: clip.duration,
              transcript: null,
            }),
          );
        }}
      />
    </div>
  );
}

function TaskComposer({
  onText,
  onVoice,
}: {
  readonly onText: (text: string) => void;
  readonly onVoice: (clip: { blob: Blob; url: string; duration: number }) => void;
}) {
  const [text, setText] = useState('');
  const [armed, setArmed] = useState(false);
  const toast = useToast();
  const recorder = useVoiceRecorder({ maxSeconds: 120 });
  const { state, reset } = recorder;

  useEffect(() => {
    if (state.status !== 'error') return;
    toast({ text: RECORDER_ERRORS[state.reason] });
    reset();
  }, [state, toast, reset]);

  const submit = () => {
    const value = text.trim();
    if (!value) return;
    onText(value);
    setText('');
  };

  if (state.status === 'preview') {
    return (
      <footer className={styles.footer}>
        <div className={styles.row}>
          <VoicePreviewBar
            clip={state.clip}
            onDiscard={() => reset()}
            onSend={() => {
              onVoice(state.clip);
              reset(true);
            }}
          />
        </div>
      </footer>
    );
  }

  const recording = state.status === 'recording' || state.status === 'requesting';
  return (
    <footer className={styles.footer}>
      <div className={styles.chips} role="group" aria-label="Быстрые поручения">
        {QUICK.map((q) => (
          <button
            key={q}
            type="button"
            className={styles.chip}
            onClick={() => onText(q)}
            disabled={recording}
          >
            {q}
          </button>
        ))}
      </div>
      <form
        className={styles.row}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {state.status === 'recording' ? (
          <VoiceRecordingBar
            startedAt={state.startedAt}
            maxSeconds={recorder.maxSeconds}
            cancelArmed={armed}
          />
        ) : (
          <>
            <label htmlFor="task" style={visuallyHiddenStyle}>
              Поручение текстом
            </label>
            <input
              id="task"
              type="text"
              className={styles.input}
              placeholder="Поручение текстом"
              enterKeyHint="send"
              autoComplete="off"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </>
        )}
        {text.trim() && !recording ? (
          <button type="submit" className={styles.big} aria-label="Отправить поручение">
            <Icon name="send" size={26} strokeWidth={2} />
          </button>
        ) : (
          <HoldToRecord
            label="Удерживайте и говорите"
            className={styles.big}
            recording={recording}
            onStart={() => void recorder.start()}
            onStop={recorder.stop}
            onCancel={recorder.cancel}
            onCancelArmedChange={setArmed}
          >
            <Icon name="mic" size={28} strokeWidth={2} />
          </HoldToRecord>
        )}
      </form>
    </footer>
  );
}
