import type { HttpCore } from '../http/client';
import { SseConnection } from '../sse/sse-connection';
import type { Unsubscribe } from '../ports/common';
import type { MasterEventHandlers, MasterEventsGateway } from '../ports/master-events-gateway';
import type { MasterEvent } from '../types';

/** Адаптер потока событий кабинета мастера. */
export class HttpMasterEventsGateway implements MasterEventsGateway {
  constructor(private readonly core: HttpCore) {}

  subscribe(handlers: MasterEventHandlers): Unsubscribe {
    const connection = new SseConnection({
      url: this.core.url('/me/events'),
      fetch: this.core.authorizedFetch,
      onFrame: (frame) => handlers.onEvent(JSON.parse(frame.data) as MasterEvent, frame.id),
      ...(handlers.onStateChange && { onStateChange: handlers.onStateChange }),
    }).start();
    return () => connection.close();
  }
}
