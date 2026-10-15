import { unwrap, type HttpCore } from '../http/client';
import type { HistoryCursor } from '../ports/common';
import type { InboxGateway } from '../ports/inbox-gateway';
import type {
  ConversationFilter,
  ConversationList,
  ConversationSummary,
  Handler,
  MasterSendResult,
  MessagePage,
  TextInput,
} from '../types';
import { cursorQuery } from './http-conversation-gateway';

/** Адаптер чатов мастера. */
export class HttpInboxGateway implements InboxGateway {
  constructor(private readonly core: HttpCore) {}

  list(filter: ConversationFilter, query?: string): Promise<ConversationList> {
    return unwrap(() =>
      this.core.api.GET('/me/conversations', {
        params: { query: { filter, ...(query ? { q: query } : {}) } },
      }),
    );
  }

  get(conversationId: string): Promise<ConversationSummary> {
    return unwrap(() =>
      this.core.api.GET('/me/conversations/{conversation_id}', {
        params: { path: { conversation_id: conversationId } },
      }),
    );
  }

  listMessages(conversationId: string, cursor: HistoryCursor = {}): Promise<MessagePage> {
    return unwrap(() =>
      this.core.api.GET('/me/conversations/{conversation_id}/messages', {
        params: { path: { conversation_id: conversationId }, query: cursorQuery(cursor) },
      }),
    );
  }

  send(conversationId: string, input: TextInput): Promise<MasterSendResult> {
    return unwrap(() =>
      this.core.api.POST('/me/conversations/{conversation_id}/messages', {
        params: { path: { conversation_id: conversationId } },
        body: input,
      }),
    );
  }

  async setHandler(conversationId: string, handler: Handler): Promise<Handler> {
    const state = await unwrap(() =>
      this.core.api.PUT('/me/conversations/{conversation_id}/handler', {
        params: { path: { conversation_id: conversationId } },
        body: { handler },
      }),
    );
    return state.handler;
  }
}
