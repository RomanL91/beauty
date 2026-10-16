import type { MasterEvent, Message, StreamState } from '@beauty/api';
import { createContext, useContext, useEffect, useRef } from 'react';

type MessageListener = (message: Message, kind: 'created' | 'updated') => void;

/**
 * Раздача событий `/me/events` лентам: диалогам по `conversation_id`,
 * поручениям — по `null`. Одна SSE-подписка на всё приложение.
 */
export class MasterEventHub {
  readonly #listeners = new Map<string | null, Set<MessageListener>>();
  #state: StreamState = 'connecting';
  readonly #stateListeners = new Set<() => void>();

  /** Подписаться на сообщения одной ленты. */
  onMessages(conversationId: string | null, listener: MessageListener): () => void {
    const set = this.#listeners.get(conversationId) ?? new Set();
    set.add(listener);
    this.#listeners.set(conversationId, set);
    return () => set.delete(listener);
  }

  readonly #resetListeners = new Set<() => void>();

  /** Поток начат заново (`reset`): ленты перечитывают историю. */
  onReset(listener: () => void): () => void {
    this.#resetListeners.add(listener);
    return () => this.#resetListeners.delete(listener);
  }

  /** Передать событие подписчикам. */
  dispatch(event: MasterEvent): void {
    if (event.type === 'reset') {
      for (const listener of this.#resetListeners) listener();
      return;
    }
    if (event.type !== 'message.created' && event.type !== 'message.updated') return;
    const kind = event.type === 'message.created' ? 'created' : 'updated';
    for (const listener of this.#listeners.get(event.conversation_id) ?? [])
      listener(event.message, kind);
  }

  get state(): StreamState {
    return this.#state;
  }

  setState(state: StreamState): void {
    this.#state = state;
    for (const l of this.#stateListeners) l();
  }

  subscribeState = (listener: () => void): (() => void) => {
    this.#stateListeners.add(listener);
    return () => this.#stateListeners.delete(listener);
  };

  getState = (): StreamState => this.#state;
}

export const EventHubContext = createContext<MasterEventHub | null>(null);

/** Хаб событий кабинета. */
export function useEventHub(): MasterEventHub {
  const hub = useContext(EventHubContext);
  if (!hub) throw new Error('useEventHub вне провайдера');
  return hub;
}

/** Слушать сообщения ленты (диалог или поручения). */
export function useFeedEvents(conversationId: string | null, listener: MessageListener): void {
  const hub = useEventHub();
  const latest = useRef(listener);
  useEffect(() => {
    latest.current = listener;
  });
  useEffect(
    () => hub.onMessages(conversationId, (m, k) => latest.current(m, k)),
    [hub, conversationId],
  );
}
