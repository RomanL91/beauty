import {
  HoldToRecord,
  Icon,
  IconButton,
  VoicePreviewBar,
  VoiceRecordingBar,
  useToast,
  useVoiceRecorder,
  visuallyHiddenStyle,
  type VoiceClip,
} from '@beauty/ui';
import { useEffect, useId, useRef, useState } from 'react';
import styles from './Composer.module.css';

const RECORDER_ERRORS = {
  denied: 'Нет доступа к микрофону — разрешите его в настройках браузера',
  unsupported: 'Этот браузер не умеет записывать голосовые — напишите текстом',
  'too-short': 'Удерживайте кнопку, пока говорите',
  failed: 'Не получилось включить микрофон',
} as const;

/**
 * Поле ввода чата: текст (Enter — отправить, Shift+Enter — новая строка) или
 * голосовое (удерживать микрофон, влево — отмена, затем превью).
 */
export function Composer({
  placeholder = 'Сообщение',
  onSendText,
  onSendVoice,
  maxVoiceSeconds = 120,
}: {
  readonly placeholder?: string;
  readonly onSendText: (text: string) => void;
  readonly onSendVoice: (clip: VoiceClip) => void;
  readonly maxVoiceSeconds?: number;
}) {
  const [text, setText] = useState('');
  const [armed, setArmed] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);
  const id = useId();
  const toast = useToast();
  const recorder = useVoiceRecorder({ maxSeconds: maxVoiceSeconds });
  const { state, reset } = recorder;

  useEffect(() => {
    if (state.status !== 'error') return;
    toast({ text: RECORDER_ERRORS[state.reason] });
    reset();
  }, [state, toast, reset]);

  // Высота поля под текст (до ~6 строк).
  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight + 2, 140)}px`;
  }, [text]);

  const submit = () => {
    const value = text.trim();
    if (!value) return;
    onSendText(value);
    setText('');
    field.current?.focus();
  };

  if (state.status === 'preview') {
    return (
      <footer className={styles.composer}>
        <VoicePreviewBar
          clip={state.clip}
          onDiscard={() => reset()}
          onSend={() => {
            onSendVoice(state.clip);
            // URL превью нужен сообщению в ленте — не отзываем.
            reset(true);
          }}
        />
      </footer>
    );
  }

  const recording = state.status === 'recording' || state.status === 'requesting';
  return (
    <footer className={styles.composer}>
      {state.status === 'recording' ? (
        <VoiceRecordingBar
          startedAt={state.startedAt}
          maxSeconds={recorder.maxSeconds}
          cancelArmed={armed}
        />
      ) : (
        <>
          <label htmlFor={id} style={visuallyHiddenStyle}>
            {placeholder}
          </label>
          <textarea
            id={id}
            ref={field}
            rows={1}
            className={styles.field}
            placeholder={placeholder}
            value={text}
            enterKeyHint="send"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
          />
        </>
      )}
      {text.trim() && !recording ? (
        <IconButton label="Отправить" look="accent" onClick={submit}>
          <Icon name="send" size={20} strokeWidth={2} />
        </IconButton>
      ) : (
        <HoldToRecord
          label="Записать голосовое: удерживайте и говорите"
          className={styles.mic}
          recording={recording}
          onStart={() => void recorder.start()}
          onStop={recorder.stop}
          onCancel={recorder.cancel}
          onCancelArmedChange={setArmed}
        >
          <Icon name="mic" size={20} strokeWidth={2} />
        </HoldToRecord>
      )}
    </footer>
  );
}
