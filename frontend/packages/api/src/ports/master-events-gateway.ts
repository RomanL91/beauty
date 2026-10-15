import type { MasterEvent } from '../types';
import type { StreamState, Unsubscribe } from './common';

/** Подписчик на события кабинета. */
export interface MasterEventHandlers {
  readonly onEvent: (event: MasterEvent, eventId: string | null) => void;
  readonly onStateChange?: (state: StreamState) => void;
}

/** Порт живых событий кабинета мастера (`/me/events`). */
export interface MasterEventsGateway {
  subscribe(handlers: MasterEventHandlers): Unsubscribe;
}
