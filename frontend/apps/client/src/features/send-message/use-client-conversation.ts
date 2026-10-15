import {
  ApiError,
  EMPTY_FEED,
  feedReducer,
  oldestMessageId,
  type ClientMessageInput,
  type Message,
  type OutgoingDraft,
  type StreamState,
} from '@beauty/api';
import type { VoiceClip } from '@beauty/ui';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { newClientId } from '../../shared/lib/client-id';
import { useContainer, useMasterSlug } from '../../shared/lib/container-context';

const PAGE_SIZE = 30;

/** Состояние первой загрузки ленты. */
export type InitialLoad =
  { status: 'loading' } | { status: 'ready' } | { status: 'error'; error: ApiError };

/**
 * Переписка клиента с администратором мастера.
 *
 * Порядок важен: сначала подписка на SSE, затем первая страница истории —
 * сообщения, пришедшие в промежутке, не теряются (дубли схлопывает редьюсер).
 * Отправка оптимистичная: сообщение сразу в ленте (`pending`), затем
 * заменяется серверным или помечается `failed` с повтором.
 */
export function useClientConversation() {
  const { conversations } = useContainer();
  const slug = useMasterSlug();
  const conversation = useQuery({
    queryKey: ['conversation', slug],
    queryFn: () => conversations.open(slug),
    staleTime: Infinity,
  });
  const conversationId = conversation.data?.id ?? null;

  const [feed, dispatch] = useReducer(feedReducer, EMPTY_FEED);
  const [stream, setStream] = useState<StreamState>('connecting');
  const [initial, setInitial] = useState<InitialLoad>({ status: 'loading' });
  const [older, setOlder] = useState<'idle' | 'loading' | 'error'>('idle');
  /** Окна, выбранные, но ещё не подтверждённые сервером: offerId → start. */
  const [picked, setPicked] = useState<ReadonlyMap<string, string>>(new Map());
  const feedRef = useRef(feed);
  useLayoutEffect(() => {
    feedRef.current = feed;
  });

  useEffect(() => {
    if (!conversationId) return undefined;
    return conversations.subscribe(conversationId, {
      onEvent: (event) =>
        dispatch({
          type: event.type === 'message.created' ? 'remote/created' : 'remote/updated',
          message: event.message,
        }),
      onStateChange: setStream,
    });
  }, [conversations, conversationId]);

  // Первая страница истории; `reload` — повтор после ошибки.
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!conversationId) return undefined;
    let cancelled = false;
    conversations.listMessages(conversationId, { limit: PAGE_SIZE }).then(
      (page) => {
        if (cancelled) return;
        dispatch({ type: 'history/loaded', page, older: false });
        setInitial({ status: 'ready' });
      },
      (error: unknown) => {
        if (!cancelled) {
          setInitial({
            status: 'error',
            error: error instanceof ApiError ? error : ApiError.network(error),
          });
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [conversations, conversationId, reload]);

  /** Повторить первую загрузку после ошибки. */
  const loadInitial = useCallback(() => {
    setInitial({ status: 'loading' });
    setReload((n) => n + 1);
  }, []);

  const loadOlder = useCallback(async () => {
    const before = oldestMessageId(feedRef.current);
    if (!conversationId || !before || !feedRef.current.hasMore) return;
    setOlder('loading');
    try {
      const page = await conversations.listMessages(conversationId, { before, limit: PAGE_SIZE });
      dispatch({ type: 'history/loaded', page, older: true });
      setOlder('idle');
    } catch {
      setOlder('error');
    }
  }, [conversations, conversationId]);

  const deliver = useCallback(
    async (clientId: string, draft: OutgoingDraft) => {
      if (!conversationId) return;
      try {
        const message =
          draft.kind === 'voice'
            ? await conversations.sendVoice(conversationId, {
                clientId,
                audio: draft.audio,
                duration: draft.duration,
              })
            : await conversations.send(conversationId, toInput(clientId, draft));
        dispatch({ type: 'local/sent', clientId, message });
      } catch {
        dispatch({ type: 'local/failed', clientId });
        if (draft.kind === 'slot_pick') {
          setPicked((map) => {
            const next = new Map(map);
            next.delete(draft.offerId);
            return next;
          });
        }
      }
    },
    [conversations, conversationId],
  );

  const enqueue = useCallback(
    (draft: OutgoingDraft, preview: Message) => {
      dispatch({ type: 'local/added', message: preview, draft });
      void deliver(preview.client_id ?? '', draft);
    },
    [deliver],
  );

  /** Отправить текст. */
  const sendText = useCallback(
    (text: string) => {
      const clientId = newClientId();
      enqueue({ kind: 'text', text }, local(clientId, { kind: 'text', text }));
    },
    [enqueue],
  );

  /** Отправить голосовое из превью. */
  const sendVoice = useCallback(
    (clip: VoiceClip) => {
      const clientId = newClientId();
      enqueue(
        { kind: 'voice', audio: clip.blob, duration: clip.duration },
        local(clientId, {
          kind: 'voice',
          audio_url: clip.url,
          duration: clip.duration,
          transcript: null,
        }),
      );
    },
    [enqueue],
  );

  /** Выбрать окно из предложения агента; `label` — как показать выбор в ленте. */
  const pickSlot = useCallback(
    (offerId: string, start: string, label: string) => {
      setPicked((map) => new Map(map).set(offerId, start));
      const clientId = newClientId();
      enqueue(
        { kind: 'slot_pick', offerId, start },
        local(clientId, { kind: 'text', text: label }),
      );
    },
    [enqueue],
  );

  /** Попросить конкретное окно (продолжение записи после входа). */
  const bookSlot = useCallback(
    (serviceId: string, start: string, label: string) => {
      const clientId = newClientId();
      enqueue(
        { kind: 'book_slot', serviceId, start },
        local(clientId, { kind: 'text', text: label }),
      );
    },
    [enqueue],
  );

  /** Повторить неотправленное. */
  const retry = useCallback(
    (clientId: string) => {
      const draft = feedRef.current.items.find((i) => i.key === `local:${clientId}`)?.draft;
      if (!draft) return;
      dispatch({ type: 'local/retry', clientId });
      if (draft.kind === 'slot_pick')
        setPicked((map) => new Map(map).set(draft.offerId, draft.start));
      void deliver(clientId, draft);
    },
    [deliver],
  );

  /** Обновить сообщение по ответу API (например, карточку после отмены). */
  const applyUpdate = useCallback(
    (message: Message) => dispatch({ type: 'remote/updated', message }),
    [],
  );

  return {
    conversation,
    conversationId,
    feed,
    stream,
    initial,
    older,
    picked,
    loadInitial,
    loadOlder,
    sendText,
    sendVoice,
    pickSlot,
    bookSlot,
    retry,
    applyUpdate,
  };
}

function toInput(
  clientId: string,
  draft: Exclude<OutgoingDraft, { kind: 'voice' }>,
): ClientMessageInput {
  switch (draft.kind) {
    case 'text':
      return { kind: 'text', client_id: clientId, text: draft.text };
    case 'slot_pick':
      return {
        kind: 'slot_pick',
        client_id: clientId,
        offer_id: draft.offerId,
        start: draft.start,
      };
    case 'book_slot':
      return {
        kind: 'book_slot',
        client_id: clientId,
        service_id: draft.serviceId,
        start: draft.start,
      };
  }
}

/** Локальное (оптимистичное) сообщение клиента. */
function local(
  clientId: string,
  body:
    | { kind: 'text'; text: string }
    | { kind: 'voice'; audio_url: string; duration: number; transcript: null },
): Message {
  return {
    id: `local:${clientId}`,
    client_id: clientId,
    author: 'client',
    ai_generated: false,
    sources: [],
    created_at: new Date().toISOString(),
    ...body,
  };
}
