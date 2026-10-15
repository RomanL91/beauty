import type {
  ConversationFilter,
  ConversationList,
  ConversationSummary,
  Handler,
  MasterSendResult,
  MessagePage,
  TextInput,
} from '../types';
import type { HistoryCursor } from './common';

/** Порт чатов мастера с клиентами. */
export interface InboxGateway {
  list(filter: ConversationFilter, query?: string): Promise<ConversationList>;
  get(conversationId: string): Promise<ConversationSummary>;
  listMessages(conversationId: string, cursor?: HistoryCursor): Promise<MessagePage>;
  /** Ответ мастера; сервер переводит диалог на мастера. */
  send(conversationId: string, input: TextInput): Promise<MasterSendResult>;
  setHandler(conversationId: string, handler: Handler): Promise<Handler>;
}
