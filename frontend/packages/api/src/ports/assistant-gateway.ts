import type { Message, MessagePage, TextInput } from '../types';
import type { HistoryCursor, VoiceDraft } from './common';

/** Порт поручений агенту (лента мастера с его администратором). */
export interface AssistantGateway {
  listMessages(cursor?: HistoryCursor): Promise<MessagePage>;
  sendText(input: TextInput): Promise<Message>;
  sendVoice(draft: VoiceDraft): Promise<Message>;
  /** Ответ на карточку выбора; возвращает её с отмеченным вариантом. */
  choose(choiceId: string, optionId: string): Promise<Message>;
}
