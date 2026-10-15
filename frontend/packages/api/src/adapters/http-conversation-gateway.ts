import { ApiError } from '../http/api-error';
import { call, unwrap, type HttpCore } from '../http/client';
import { SseConnection } from '../sse/sse-connection';
import type { HistoryCursor, Unsubscribe, VoiceDraft } from '../ports/common';
import type {
  ConversationGateway,
  ConversationStreamHandlers,
} from '../ports/conversation-gateway';
import type {
  Appointment,
  ClientConversation,
  ClientMessageInput,
  ConversationEvent,
  Message,
  MessagePage,
} from '../types';
import { postVoice } from './multipart';

/** Адаптер переписки клиента. */
export class HttpConversationGateway implements ConversationGateway {
  constructor(private readonly core: HttpCore) {}

  async open(masterSlug: string): Promise<ClientConversation> {
    const params = { query: { master: masterSlug } };
    const found = await call(() => this.core.api.GET('/conversations/me', { params }));
    if (found.data) return found.data;
    if (found.response.status !== 404) throw ApiError.fromBody(found.response.status, found.error);
    return unwrap(() => this.core.api.POST('/conversations/me', { params }));
  }

  listMessages(conversationId: string, cursor: HistoryCursor = {}): Promise<MessagePage> {
    return unwrap(() =>
      this.core.api.GET('/conversations/{conversation_id}/messages', {
        params: { path: { conversation_id: conversationId }, query: cursorQuery(cursor) },
      }),
    );
  }

  send(conversationId: string, input: ClientMessageInput): Promise<Message> {
    return unwrap(() =>
      this.core.api.POST('/conversations/{conversation_id}/messages', {
        params: { path: { conversation_id: conversationId } },
        body: input,
      }),
    );
  }

  sendVoice(conversationId: string, draft: VoiceDraft): Promise<Message> {
    return postVoice(
      this.core,
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
      draft,
    );
  }

  subscribe(
    conversationId: string,
    handlers: ConversationStreamHandlers,
    lastEventId: string | null = null,
  ): Unsubscribe {
    const connection = new SseConnection({
      url: this.core.url(`/conversations/${encodeURIComponent(conversationId)}/events`),
      fetch: this.core.authorizedFetch,
      lastEventId,
      onFrame: (frame) => {
        handlers.onEvent(JSON.parse(frame.data) as ConversationEvent, frame.id);
      },
      ...(handlers.onStateChange && { onStateChange: handlers.onStateChange }),
      ...(handlers.onFatal && { onFatal: handlers.onFatal }),
    }).start();
    return () => connection.close();
  }

  cancelAppointment(appointmentId: string): Promise<Appointment> {
    return unwrap(() =>
      this.core.api.POST('/appointments/{appointment_id}/cancel', {
        params: { path: { appointment_id: appointmentId } },
        body: {},
      }),
    );
  }

  rescheduleAppointment(appointmentId: string, start: string): Promise<Appointment> {
    return unwrap(() =>
      this.core.api.POST('/appointments/{appointment_id}/reschedule', {
        params: { path: { appointment_id: appointmentId } },
        body: { start },
      }),
    );
  }
}

/** Курсор истории → query-параметры. */
export function cursorQuery(cursor: HistoryCursor): { before?: string; limit?: number } {
  return {
    ...(cursor.before !== undefined && { before: cursor.before }),
    ...(cursor.limit !== undefined && { limit: cursor.limit }),
  };
}
