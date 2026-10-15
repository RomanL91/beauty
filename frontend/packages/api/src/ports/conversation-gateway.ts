import type {
  Appointment,
  ClientConversation,
  ClientMessageInput,
  ConversationEvent,
  Message,
  MessagePage,
} from '../types';
import type { HistoryCursor, StreamState, Unsubscribe, VoiceDraft } from './common';

/** Подписчик на поток переписки. */
export interface ConversationStreamHandlers {
  readonly onEvent: (event: ConversationEvent, eventId: string | null) => void;
  readonly onStateChange?: (state: StreamState) => void;
  /** Поток остановлен окончательно (например, переписка недоступна). */
  readonly onFatal?: (error: Error) => void;
}

/** Порт переписки клиента с администратором мастера. */
export interface ConversationGateway {
  /** Найти или открыть переписку с мастером. */
  open(masterSlug: string): Promise<ClientConversation>;
  /** Страница истории (по возрастанию времени). */
  listMessages(conversationId: string, cursor?: HistoryCursor): Promise<MessagePage>;
  /** Текст или выбор слота. */
  send(conversationId: string, input: ClientMessageInput): Promise<Message>;
  /** Голосовое (multipart). */
  sendVoice(conversationId: string, draft: VoiceDraft): Promise<Message>;
  /** Живой поток событий с `Last-Event-ID`. */
  subscribe(
    conversationId: string,
    handlers: ConversationStreamHandlers,
    lastEventId?: string | null,
  ): Unsubscribe;
  cancelAppointment(appointmentId: string): Promise<Appointment>;
  rescheduleAppointment(appointmentId: string, start: string): Promise<Appointment>;
}
