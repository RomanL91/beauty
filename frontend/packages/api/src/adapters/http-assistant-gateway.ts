import { unwrap, type HttpCore } from '../http/client';
import type { AssistantGateway } from '../ports/assistant-gateway';
import type { HistoryCursor, VoiceDraft } from '../ports/common';
import type { Message, MessagePage, TextInput } from '../types';
import { cursorQuery } from './http-conversation-gateway';
import { postVoice } from './multipart';

/** Адаптер поручений агенту. */
export class HttpAssistantGateway implements AssistantGateway {
  constructor(private readonly core: HttpCore) {}

  listMessages(cursor: HistoryCursor = {}): Promise<MessagePage> {
    return unwrap(() =>
      this.core.api.GET('/me/assistant/messages', { params: { query: cursorQuery(cursor) } }),
    );
  }

  sendText(input: TextInput): Promise<Message> {
    return unwrap(() => this.core.api.POST('/me/assistant/messages', { body: input }));
  }

  sendVoice(draft: VoiceDraft): Promise<Message> {
    return postVoice(this.core, '/me/assistant/messages', draft);
  }

  choose(choiceId: string, optionId: string): Promise<Message> {
    return unwrap(() =>
      this.core.api.POST('/me/assistant/choices/{choice_id}', {
        params: { path: { choice_id: choiceId } },
        body: { option_id: optionId },
      }),
    );
  }
}
