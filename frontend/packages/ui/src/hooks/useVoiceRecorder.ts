import { useCallback, useEffect, useRef, useState } from 'react';

/** Записанное голосовое до отправки. */
export interface VoiceClip {
  readonly blob: Blob;
  readonly url: string;
  /** Секунды. */
  readonly duration: number;
}

/** Состояние записи. */
export type RecorderState =
  | { readonly status: 'idle' }
  | { readonly status: 'requesting' }
  | { readonly status: 'recording'; readonly startedAt: number }
  | { readonly status: 'preview'; readonly clip: VoiceClip }
  | {
      readonly status: 'error';
      readonly reason: 'denied' | 'unsupported' | 'too-short' | 'failed';
    };

/**
 * Форматы по приоритету: Chrome/Firefox/Android пишут webm/opus, iOS Safari —
 * только mp4/aac.
 */
const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/aac',
];

/** Первый поддерживаемый браузером формат (или `undefined` — на усмотрение браузера). */
export function pickAudioMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return undefined;
  }
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
}

const MIN_SECONDS = 0.6;

/**
 * Запись голосового через MediaRecorder.
 *
 * `start` → `stop` даёт превью (`preview`), `cancel` — выбрасывает запись.
 * Длительность ограничена `maxSeconds`: по достижении запись останавливается
 * сама и уходит в превью. Слишком короткое нажатие — подсказка `too-short`.
 */
export function useVoiceRecorder({ maxSeconds = 120 }: { maxSeconds?: number } = {}) {
  const [state, setState] = useState<RecorderState>({ status: 'idle' });
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const startedAt = useRef(0);
  const intent = useRef<'keep' | 'drop' | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clipUrl = useRef<string | null>(null);

  const releaseStream = useCallback(() => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const finish = useCallback((mode: 'keep' | 'drop') => {
    const active = recorder.current;
    if (!active) {
      // Отпустили раньше, чем браузер дал микрофон: доделаем после старта.
      intent.current = mode;
      return;
    }
    intent.current = mode;
    if (active.state !== 'inactive') active.stop();
  }, []);

  const start = useCallback(async () => {
    if (
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === 'undefined'
    ) {
      setState({ status: 'error', reason: 'unsupported' });
      return;
    }
    intent.current = null;
    chunks.current = [];
    setState({ status: 'requesting' });
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      const denied =
        error instanceof DOMException &&
        (error.name === 'NotAllowedError' || error.name === 'SecurityError');
      setState({ status: 'error', reason: denied ? 'denied' : 'failed' });
      return;
    }
    const mimeType = pickAudioMimeType();
    const media = new MediaRecorder(stream.current, mimeType ? { mimeType } : undefined);
    recorder.current = media;
    media.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.current.push(e.data);
    };
    media.onstop = () => {
      const duration = (Date.now() - startedAt.current) / 1000;
      const keep = intent.current !== 'drop';
      recorder.current = null;
      releaseStream();
      if (!keep) {
        setState({ status: 'idle' });
        return;
      }
      if (duration < MIN_SECONDS) {
        setState({ status: 'error', reason: 'too-short' });
        return;
      }
      const blob = new Blob(chunks.current, { type: media.mimeType || mimeType || 'audio/webm' });
      if (clipUrl.current) URL.revokeObjectURL(clipUrl.current);
      clipUrl.current = URL.createObjectURL(blob);
      setState({
        status: 'preview',
        clip: { blob, url: clipUrl.current, duration: Math.min(duration, maxSeconds) },
      });
    };
    startedAt.current = Date.now();
    media.start(250);
    setState({ status: 'recording', startedAt: startedAt.current });
    timer.current = setTimeout(() => finish('keep'), maxSeconds * 1000);
    if (intent.current !== null) finish(intent.current);
  }, [finish, maxSeconds, releaseStream]);

  const stop = useCallback(() => finish('keep'), [finish]);
  const cancel = useCallback(() => finish('drop'), [finish]);

  /**
   * Убрать превью / ошибку. `keepUrl` — запись ушла в ленту и её URL ещё
   * нужен для прослушивания: не отзывать.
   */
  const reset = useCallback((keepUrl = false) => {
    if (clipUrl.current && !keepUrl) URL.revokeObjectURL(clipUrl.current);
    clipUrl.current = null;
    setState({ status: 'idle' });
  }, []);

  useEffect(
    () => () => {
      if (recorder.current && recorder.current.state !== 'inactive') {
        intent.current = 'drop';
        recorder.current.stop();
      }
      releaseStream();
      if (clipUrl.current) URL.revokeObjectURL(clipUrl.current);
    },
    [releaseStream],
  );

  return { state, start, stop, cancel, reset, maxSeconds };
}
