import type { Message, MessagePage } from '../types';

/** Состояние доставки сообщения. */
export type Delivery = 'pending' | 'sent' | 'failed';

/** Что отправляли (для повтора упавшего сообщения). */
export type OutgoingDraft =
  | { readonly kind: 'text'; readonly text: string }
  | { readonly kind: 'voice'; readonly audio: Blob; readonly duration: number }
  | { readonly kind: 'slot_pick'; readonly offerId: string; readonly start: string }
  | { readonly kind: 'book_slot'; readonly serviceId: string; readonly start: string };

/** Элемент ленты: сообщение сервера или локальное (ещё не подтверждённое). */
export interface FeedItem {
  /** Ключ для React: `id` сервера или `local:<client_id>`. */
  readonly key: string;
  readonly message: Message;
  readonly delivery: Delivery;
  /** Только у локальных: что повторить при ошибке. */
  readonly draft?: OutgoingDraft;
}

/** Лента сообщений. */
export interface FeedState {
  readonly items: readonly FeedItem[];
  /** Есть ли сообщения старше загруженных. */
  readonly hasMore: boolean;
  /** Загружена ли первая страница. */
  readonly loaded: boolean;
}

/** Действия ленты. */
export type FeedAction =
  | { readonly type: 'history/loaded'; readonly page: MessagePage; readonly older: boolean }
  | { readonly type: 'local/added'; readonly message: Message; readonly draft: OutgoingDraft }
  | { readonly type: 'local/sent'; readonly clientId: string; readonly message: Message }
  | { readonly type: 'local/failed'; readonly clientId: string }
  | { readonly type: 'local/retry'; readonly clientId: string }
  | { readonly type: 'local/discarded'; readonly clientId: string }
  | { readonly type: 'remote/created'; readonly message: Message }
  | { readonly type: 'remote/updated'; readonly message: Message };

/** Пустая лента. */
export const EMPTY_FEED: FeedState = { items: [], hasMore: false, loaded: false };

const localKey = (clientId: string): string => `local:${clientId}`;

/**
 * Редьюсер ленты: сливает историю, оптимистичные сообщения и события SSE.
 *
 * * Дедупликация по `id` сервера: SSE после переподключения и история могут
 *   прислать одно сообщение дважды.
 * * Локальное сообщение (`pending`/`failed`) заменяется серверным по
 *   `client_id` — что бы ни пришло первым: ответ POST или событие SSE.
 * * Порядок — по `created_at`; локальные (ещё без серверного времени) — в конце.
 */
export function feedReducer(state: FeedState, action: FeedAction): FeedState {
  switch (action.type) {
    case 'history/loaded': {
      let items = state.items;
      for (const message of action.page.items) items = upsert(items, message);
      return {
        items,
        hasMore: action.older || !state.loaded ? action.page.has_more : state.hasMore,
        loaded: true,
      };
    }
    case 'local/added':
      return {
        ...state,
        items: [
          ...state.items,
          {
            key: localKey(action.message.client_id ?? action.message.id),
            message: action.message,
            delivery: 'pending',
            draft: action.draft,
          },
        ],
      };
    case 'local/sent':
      return { ...state, items: upsert(state.items, action.message) };
    case 'local/failed':
      return patchLocal(state, action.clientId, 'failed');
    case 'local/retry':
      return patchLocal(state, action.clientId, 'pending');
    case 'local/discarded':
      return { ...state, items: state.items.filter((i) => i.key !== localKey(action.clientId)) };
    case 'remote/created':
    case 'remote/updated':
      return { ...state, items: upsert(state.items, action.message) };
  }
}

/** Вставить или заменить серверное сообщение. */
function upsert(items: readonly FeedItem[], message: Message): readonly FeedItem[] {
  const local = message.client_id ? localKey(message.client_id) : null;
  const index = items.findIndex((i) => i.key === message.id || (local !== null && i.key === local));
  const item: FeedItem = { key: message.id, message, delivery: 'sent' };
  if (index !== -1) {
    const next = items.slice();
    next.splice(index, 1);
    return insertSorted(next, item);
  }
  return insertSorted(items, item);
}

/** Вставка с сохранением порядка: серверные по времени, локальные — после них. */
function insertSorted(items: readonly FeedItem[], item: FeedItem): readonly FeedItem[] {
  const time = Date.parse(item.message.created_at);
  let at = items.length;
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const other = items[i]!;
    if (other.delivery !== 'sent') {
      at = i;
      continue;
    }
    if (Date.parse(other.message.created_at) > time) {
      at = i;
      continue;
    }
    break;
  }
  const next = items.slice();
  next.splice(at, 0, item);
  return next;
}

function patchLocal(state: FeedState, clientId: string, delivery: Delivery): FeedState {
  return {
    ...state,
    items: state.items.map((i) => (i.key === localKey(clientId) ? { ...i, delivery } : i)),
  };
}

/** `id` самого старого серверного сообщения — курсор подгрузки истории. */
export function oldestMessageId(state: FeedState): string | undefined {
  return state.items.find((i) => i.delivery === 'sent')?.message.id;
}
