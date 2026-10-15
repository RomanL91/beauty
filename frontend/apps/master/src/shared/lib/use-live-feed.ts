import {
  ApiError,
  EMPTY_FEED,
  feedReducer,
  oldestMessageId,
  type HistoryCursor,
  type Message,
  type MessagePage,
  type OutgoingDraft,
} from '@beauty/api';
import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { useFeedEvents } from './events';

const PAGE_SIZE = 30;

/** Как ленте загрузить историю и отправить сообщение. */
export interface LiveFeedSource {
  /** `null` — поручения, иначе id диалога (ключ событий хаба). */
  readonly channel: string | null;
  readonly load: (cursor: HistoryCursor) => Promise<MessagePage>;
  readonly deliver: (clientId: string, draft: OutgoingDraft) => Promise<Message>;
}

/** Первая загрузка ленты. */
export type InitialLoad =
  { status: 'loading' } | { status: 'ready' } | { status: 'error'; error: ApiError };

/**
 * Живая лента кабинета: история (с подгрузкой вверх), события из общего
 * SSE-потока и оптимистичная отправка с повтором. Слияние — общим
 * `feedReducer` (дедупликация по id и client_id).
 */
export function useLiveFeed(source: LiveFeedSource) {
  const [feed, dispatch] = useReducer(feedReducer, EMPTY_FEED);
  const [initial, setInitial] = useState<InitialLoad>({ status: 'loading' });
  const [older, setOlder] = useState<'idle' | 'loading' | 'error'>('idle');
  const [reload, setReload] = useState(0);
  const feedRef = useRef(feed);
  const sourceRef = useRef(source);
  useLayoutEffect(() => {
    feedRef.current = feed;
    sourceRef.current = source;
  });

  useFeedEvents(source.channel, (message, kind) =>
    dispatch({ type: kind === 'created' ? 'remote/created' : 'remote/updated', message }),
  );

  const { load } = source;
  useEffect(() => {
    let cancelled = false;
    load({ limit: PAGE_SIZE }).then(
      (page) => {
        if (cancelled) return;
        dispatch({ type: 'history/loaded', page, older: false });
        setInitial({ status: 'ready' });
      },
      (error: unknown) => {
        if (!cancelled)
          setInitial({
            status: 'error',
            error: error instanceof ApiError ? error : ApiError.network(error),
          });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load, reload]);

  const retryInitial = useCallback(() => {
    setInitial({ status: 'loading' });
    setReload((n) => n + 1);
  }, []);

  const loadOlder = useCallback(async () => {
    const before = oldestMessageId(feedRef.current);
    if (!before || !feedRef.current.hasMore) return;
    setOlder('loading');
    try {
      const page = await sourceRef.current.load({ before, limit: PAGE_SIZE });
      dispatch({ type: 'history/loaded', page, older: true });
      setOlder('idle');
    } catch {
      setOlder('error');
    }
  }, []);

  const deliver = useCallback(
    async (clientId: string, draft: OutgoingDraft): Promise<Message | null> => {
      try {
        const message = await sourceRef.current.deliver(clientId, draft);
        dispatch({ type: 'local/sent', clientId, message });
        return message;
      } catch {
        dispatch({ type: 'local/failed', clientId });
        return null;
      }
    },
    [],
  );

  /** Добавить оптимистичное сообщение и отправить. */
  const send = useCallback(
    (clientId: string, draft: OutgoingDraft, preview: Message) => {
      dispatch({ type: 'local/added', message: preview, draft });
      return deliver(clientId, draft);
    },
    [deliver],
  );

  const retry = useCallback(
    (clientId: string) => {
      const draft = feedRef.current.items.find((i) => i.key === `local:${clientId}`)?.draft;
      if (!draft) return;
      dispatch({ type: 'local/retry', clientId });
      void deliver(clientId, draft);
    },
    [deliver],
  );

  const applyUpdate = useCallback(
    (message: Message) => dispatch({ type: 'remote/updated', message }),
    [],
  );

  return { feed, initial, older, retryInitial, loadOlder, send, retry, applyUpdate };
}

/** Локальное сообщение мастера (до ответа сервера). */
export function localMessage(
  clientId: string,
  body:
    | { kind: 'text'; text: string }
    | { kind: 'voice'; audio_url: string; duration: number; transcript: null },
): Message {
  return {
    id: `local:${clientId}`,
    client_id: clientId,
    author: 'master',
    ai_generated: false,
    sources: [],
    created_at: new Date().toISOString(),
    ...body,
  };
}
